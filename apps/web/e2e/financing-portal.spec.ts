import { expect, test, type Browser, type Page } from "@playwright/test";
import { clearInbox, DEMO_TENANT_ID, OTHER_TENANT_ID, signInLink } from "./fixtures";
import type { APIRequestContext } from "@playwright/test";

// P3-06 acceptance (ADR-050): walk a synthetic financing application to a logged decision and
// see the loan's schedule; a decline shows its reasons to the buyer; nothing financing-related
// exists on any other tenant. Runs signed in as portal+<viewport>@demo.cornerpin.test.

const viewport = (name: string) => name.replace("-portal", "");
// Available land lots no other test or the financing seed uses, one per project.
const LOTS: Record<string, string> = { mobile: "2-10", desktop: "3-3" };
const RISK = /risk · (\d+%)/;

async function choose(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

/** A browser signed in as `email`, through the API as portal.setup.ts does. */
async function signedIn(browser: Browser, request: APIRequestContext, email: string): Promise<Page> {
  const page = await (await browser.newContext({ storageState: { cookies: [], origins: [] } })).newPage();
  await clearInbox(request, email);
  const asked = await page.request.post("/v1/auth/magic-link", {
    data: { email, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/" },
  });
  expect(asked.status()).toBe(202);
  const token = new URL(await signInLink(request, email)).searchParams.get("token");
  expect((await page.request.post("/v1/auth/magic-link/verify", { data: { token } })).ok()).toBe(
    true,
  );
  return page;
}

async function apply(buyer: Page, number: string, name: string, income: string) {
  await buyer.goto(`/juniper-bench/lots/${number}`);
  const offer = buyer.getByRole("region", { name: /Owner financing/ });
  await expect(offer).toContainText("no credit check");
  await offer.getByLabel("Name on the application").fill(name);
  await choose(buyer, "Yearly income (a range)", income);
  await expect(offer).toContainText(/About \$[\d,]+\.\d\d a month/);
  await offer.getByRole("button", { name: "Apply to finance this lot" }).click();
  await expect(buyer.getByRole("status")).toContainText("Application sent.");
}

/** The pending application from `name`, once its score has arrived. */
async function scored(page: Page, name: string) {
  const card = page
    .getByRole("listitem")
    .filter({ hasText: name })
    .filter({ hasText: "Waiting for a decision" });
  await expect(async () => {
    await page.reload();
    await expect(card.getByText(RISK)).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 20_000 });
  return card;
}

test("a buyer's application is declined with reasons they see, and a second is approved into a loan with its schedule", async ({
  page,
  browser,
  request,
}, testInfo) => {
  test.setTimeout(90_000);
  const view = viewport(testInfo.project.name);
  const number = LOTS[view] ?? "2-10";
  const name = `Rowan ${view}`;
  const buyer = await signedIn(browser, request, `financing+${view}-${Date.now()}@buyers.cornerpin.test`);

  // A first application, on a modest stated income: the owner declines it, saying why.
  await apply(buyer, number, name, "Under $50,000");
  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: "Financing (demo)" }).click();
  await expect(page).toHaveURL(/\/financing$/);
  let card = await scored(page, name);
  await expect(card).toContainText("Risk of falling behind");
  await expect(card).toContainText("Advisory");
  await card.getByRole("button", { name: `Decline financing for ${name}` }).click();
  await card.getByLabel("Why not? The buyer is shown this.").fill("The payment is too high for the income.");
  await card.getByRole("button", { name: "Decline", exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: name }).first()).toContainText(
    "Declined: The payment is too high for the income.",
  );

  // The buyer sees the decline, with its principal reasons, in the shape of a notice.
  await buyer.goto("/account");
  const notice = buyer.getByRole("note", { name: "Why it wasn't approved" });
  await expect(notice).toContainText("The payment is too high for the income.");
  await expect(notice).toContainText("principal reasons");
  expect(await notice.getByRole("listitem").count()).toBeGreaterThanOrEqual(1);

  // A second application, with more income behind it: approved, it opens a loan.
  await apply(buyer, number, name, "Over $150,000");
  card = await scored(page, name);
  await card.getByRole("button", { name: `Approve financing for ${name}` }).click();
  await expect(card).toHaveCount(0);

  const loans = page.getByRole("region", { name: "Loans" });
  await loans.getByRole("link", { name }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  const schedule = page.getByRole("region", { name: "Schedule" });
  await expect(schedule.getByRole("row")).toHaveCount(361); // a header and 30 years of months
  await expect(schedule.getByRole("row").last()).toContainText("$0.00");

  await page.getByRole("button", { name: "Record payment" }).click();
  await expect(page.getByText("Payment recorded.")).toBeVisible();
  const payments = page.getByRole("region", { name: "Payments" });
  await expect(payments.getByRole("listitem")).toHaveCount(1);
  await expect(payments).toContainText(`portal+${view}@demo.cornerpin.test`);

  await buyer.goto("/account");
  await expect(buyer.getByRole("region", { name: /Financing applications/ })).toContainText("Approved");
});

test("another tenant has no financing anywhere", async ({ page, browser, request }, testInfo) => {
  // One project only: the other tenant's owner shares one inbox across projects.
  test.skip(viewport(testInfo.project.name) !== "desktop", "one sign-in for the other tenant");
  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await expect(page.getByRole("link", { name: "Financing (demo)" })).toBeVisible();

  const other = await signedIn(browser, request, "owner@other.cornerpin.test");
  await other.goto(`/app/${OTHER_TENANT_ID}`);
  await expect(other.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(other.getByRole("link", { name: /Financing/ })).toHaveCount(0);
  await other.goto(`/app/${OTHER_TENANT_ID}/financing`);
  await expect(other.getByText("This page could not be found.")).toBeVisible();
  const api = await other.request.get(`/v1/tenants/${OTHER_TENANT_ID}/financing/applications`);
  expect(api.status()).toBe(404);
});
