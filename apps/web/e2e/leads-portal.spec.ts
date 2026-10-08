import { expect, test, type Page } from "@playwright/test";
import { DEMO_LOTS, DEMO_TENANT_ID, signInLink } from "./fixtures";

// P2-02 acceptance: an inquiry appears as a lead; the owner changes its stage and sees it on the
// timeline. P3-03 acceptance: the owner sees a score with reasons, decides a hold, and the
// timeline shows who decided, when, and the score they saw. Runs signed in as
// portal+<viewport>@demo.cornerpin.test; visitors and buyers get their own browser contexts.

const viewport = (name: string) => name.replace("-portal", "");
// Each project holds its own available land lot, apart from the buyer tests' lots.
const SCORED_HOLD_LOTS: Record<string, string> = { mobile: "3-8", desktop: "3-10" };
const RISK = /risk · (\d+%)/;

async function choose(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

test("an inquiry becomes a lead, and the owner's stage change and note go on its timeline", async ({
  page,
  browser,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const email = `lead+${view}-${Date.now()}@example.test`;
  const question = `Is there room for a shop? (${view})`;
  const lot = `Lot ${DEMO_LOTS.home}, Juniper Bench`;

  const visitor = await (
    await browser.newContext({ storageState: { cookies: [], origins: [] } })
  ).newPage();
  await visitor.goto(`/juniper-bench/lots/${DEMO_LOTS.home}`);
  // Enabled means hydrated with a Turnstile token; typing before hydration would be lost.
  const send = visitor.getByRole("button", { name: "Send question" });
  await expect(send).toBeEnabled({ timeout: 15_000 });
  await visitor.getByLabel("Your name").fill("Lee Lead");
  await visitor.getByLabel("Email").fill(email);
  await visitor.getByLabel("Your question").fill(question);
  await send.click();
  await expect(visitor.getByRole("status")).toContainText("Sent.");

  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: /^Leads/ }).click();
  const card = page.getByRole("listitem").filter({ hasText: email });
  await expect(card).toContainText("New");
  await expect(card).toContainText(lot);
  await expect(card).toContainText("Email not verified");
  await card.getByRole("link", { name: "Lee Lead" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Lee Lead" })).toBeVisible();
  const timeline = page.getByRole("region", { name: "Timeline" });
  await expect(timeline).toContainText(`Asked about ${lot}`);
  await expect(timeline).toContainText(question);

  await choose(page, "Stage", "Contacted");
  await expect(timeline).toContainText("Stage: New → Contacted");
  await expect(timeline).toContainText(`portal+${view}@demo.cornerpin.test`);

  await page.getByLabel("Add a note").fill("Left a voicemail.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(timeline).toContainText("Left a voicemail.");
  await expect(page.getByLabel("Add a note")).toHaveValue("");

  // The stage filter finds it.
  await page
    .getByRole("navigation", { name: "Breadcrumb" })
    .getByRole("link", { name: "Leads" })
    .click();
  await page.getByRole("link", { name: /^Contacted \(/ }).click();
  await expect(page.getByRole("listitem").filter({ hasText: email })).toBeVisible();
});

test("the owner sees a lead's score and reasons, decides its hold, and the decision is logged with that score", async ({
  page,
  browser,
  request,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const number = SCORED_HOLD_LOTS[view] ?? "3-8";
  const lot = `Lot ${number}, Juniper Bench`;
  const buyerName = `Sky ${view}`;
  const email = `scored+${view}-${Date.now()}@buyers.cornerpin.test`;

  // A new buyer signs in (through the API, as portal.setup.ts does) and asks to hold the lot.
  const buyer = await (
    await browser.newContext({ storageState: { cookies: [], origins: [] } })
  ).newPage();
  const asked = await buyer.request.post("/v1/auth/magic-link", {
    data: { email, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/" },
  });
  expect(asked.status()).toBe(202);
  const token = new URL(await signInLink(request, email)).searchParams.get("token");
  expect((await buyer.request.post("/v1/auth/magic-link/verify", { data: { token } })).ok()).toBe(
    true,
  );
  await buyer.goto(`/juniper-bench/lots/${number}`);
  await buyer.getByLabel("Ask the owner to hold this lot").check();
  await buyer.getByLabel("Your name").fill(buyerName);
  await buyer.getByRole("button", { name: "Request a hold" }).click();
  await expect(buyer.getByRole("status")).toContainText("Hold requested.");

  // The hold shows the lead's advisory risk. Scores are written in the background.
  await page.goto(`/app/${DEMO_TENANT_ID}/inquiries`);
  const hold = page.getByRole("listitem").filter({ hasText: buyerName });
  await expect(async () => {
    await page.reload();
    await expect(hold.getByText(RISK)).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 20_000 });
  const percent = RISK.exec((await hold.getByText(RISK).textContent()) ?? "")?.[1] ?? "";

  // Its reasons are on the lead's page, marked as advice from a model on synthetic data.
  await hold.getByRole("link", { name: "Why this risk?" }).click();
  const panel = page.getByRole("region", { name: "Risk of falling through" });
  await expect(panel).toContainText("Advisory");
  await expect(panel).toContainText(percent);
  await expect(panel).toContainText("trained on synthetic data");
  expect(await panel.getByRole("listitem").count()).toBeGreaterThanOrEqual(3);

  // The owner approves, having seen that score.
  await page.goBack();
  await hold.getByRole("button", { name: `Approve hold for ${buyerName}` }).click();
  await expect(hold).toContainText("Approved");

  await hold.getByRole("link", { name: "Lead" }).click();
  const decision = page
    .getByRole("region", { name: "Timeline" })
    .getByRole("listitem")
    .filter({ hasText: `Decision: approved the hold on ${lot}` });
  await expect(decision).toContainText(`Risk shown: ${percent}`);
  await expect(decision).toContainText(`portal+${view}@demo.cornerpin.test`);
  await expect(decision).toContainText(/\d{1,2}:\d{2}/);
});
