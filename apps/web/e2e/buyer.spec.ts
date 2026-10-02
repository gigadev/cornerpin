import { expect, test, type Browser, type Page } from "@playwright/test";
import { DEMO_LOTS, DEMO_TENANT_ID, mailTo, type Mail } from "./fixtures";

// P1-08 acceptance: an inquiry reaches the owner; consent is recorded with its channel and
// time. P1-09 acceptance: a status change produces exactly one email per saver, in Mailpit.
// Runs signed in as buyer+<viewport>@buyers.cornerpin.test; the owner's side uses the portal
// session saved by portal.setup.ts.

const viewport = (name: string) => name.replace("-buyer", "");
// Each project holds its own available, land-only lot, so parallel runs never collide and the
// public page's filter counts (which look at lots with homes) are unaffected.
const HOLD_LOTS: Record<string, string> = { mobile: "3-4", desktop: "3-5" };
// Likewise for the lot whose status change is emailed to its savers.
const ALERT_LOTS: Record<string, string> = { mobile: "3-6", desktop: "3-7" };

/** Wait for `count` matching emails, then make sure no more arrive. */
async function expectMail(read: () => Promise<Mail[]>, count: number): Promise<Mail[]> {
  await expect.poll(async () => (await read()).length, { timeout: 15_000 }).toBe(count);
  await new Promise((resolve) => setTimeout(resolve, 2_500));
  const mail = await read();
  expect(mail).toHaveLength(count);
  return mail;
}

async function ownerPage(browser: Browser, view: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: `playwright/.auth/portal-${view}.json`,
  });
  return context.newPage();
}

test("a visitor asks about a lot without signing in, and the owner sees it", async ({
  browser,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const question = `Is the well shared? (${view} ${Date.now()})`;
  const visitor = await (await browser.newContext({ storageState: { cookies: [], origins: [] } })).newPage();

  const { home } = DEMO_LOTS;
  await visitor.goto(`/juniper-bench/lots/${home}`);
  await visitor.getByRole("link", { name: "Contact the owner" }).click();
  await visitor.getByLabel("Your name").fill("Walk-in Visitor");
  await visitor.getByLabel("Email").fill(`walkin+${view}@example.test`);
  await visitor.getByLabel("Phone (optional)").fill("208-555-0142");
  await visitor.getByLabel("Your question").fill(question);
  // Signed out, nobody is asked for contact permission (ADR-028).
  await expect(visitor.getByLabel("Email me about their lots")).toHaveCount(0);
  // Cloudflare's test site key passes without interaction once the widget has loaded.
  const send = visitor.getByRole("button", { name: "Send question" });
  await expect(send).toBeEnabled({ timeout: 15_000 });
  await send.click();
  await expect(visitor.getByRole("status")).toHaveText(
    `Sent. The owner will reply to walkin+${view}@example.test.`,
  );

  // Saving needs an account: the button signs in and comes back here.
  await visitor.getByRole("link", { name: "Save this lot" }).click();
  await expect(visitor).toHaveURL(
    (url) => url.pathname === "/signin" && url.search === `?next=%2Fjuniper-bench%2Flots%2F${home}`,
  );

  const owner = await ownerPage(browser, view);
  await owner.goto(`/app/${DEMO_TENANT_ID}`);
  await owner.getByRole("link", { name: /Inquiries and holds/ }).click();
  const inquiry = owner.getByRole("listitem").filter({ hasText: question });
  await expect(inquiry).toContainText(`Lot ${home}, Juniper Bench`);
  await expect(inquiry).toContainText("+12085550142");
  await expect(inquiry).toContainText("Email not verified");
  await expect(inquiry).toContainText("Reply only");

  // P1-09: each owner gets the question by email, with the visitor as the reply address.
  const ownerEmail = `portal+${view}@demo.cornerpin.test`;
  const [mail] = await expectMail(async () => {
    const all = await mailTo(owner.request, ownerEmail, `New question about Lot ${home}`);
    return all.filter((m) => m.text.includes(question));
  }, 1);
  expect(mail?.text).toContain(`Walk-in Visitor (walkin+${view}@example.test, +12085550142)`);
});

test("a buyer saves a lot and finds it on their account page", async ({ page }) => {
  const lot = DEMO_LOTS.otherHome;
  await page.goto(`/juniper-bench/lots/${lot}`);
  const save = page.getByRole("button", { name: "Save this lot" });
  await save.click();
  await expect(page.getByRole("button", { name: "Saved" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await page.getByRole("link", { name: "Account" }).click();
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  const saved = page.getByRole("region", { name: "Saved lots" });
  await expect(saved.getByRole("link", { name: `Lot ${lot}, Juniper Bench` })).toBeVisible();

  await saved.getByRole("button", { name: `Remove lot ${lot}` }).click();
  // Other tests in this project save lots with the same buyer, so look for this one only.
  await expect(saved.getByRole("link", { name: `Lot ${lot}, Juniper Bench` })).toHaveCount(0);
});

test("a buyer asks for a hold with email permission, and the owner's approval puts the lot on hold", async ({
  page,
  browser,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const number = HOLD_LOTS[view] ?? "3-4";
  const buyerName = `Pat ${view}`;

  await page.goto(`/juniper-bench/lots/${number}`);
  await page.getByLabel("Ask the owner to hold this lot").check();
  await page.getByLabel("Your name").fill(buyerName);
  await page.getByLabel("Message (optional)").fill("Back from the bank on Friday.");
  await page.getByLabel("Email me about their lots").click();
  await page.getByRole("button", { name: "Request a hold" }).click();
  await expect(page.getByRole("status")).toContainText("Hold requested.");
  await page.getByRole("button", { name: "Send another message" }).click();
  // One pending request per lot: the hold option is gone until the owner decides.
  await expect(page.getByLabel("Ask the owner to hold this lot")).toHaveCount(0);
  await expect(page.getByText("You've asked the owner to hold this lot.")).toBeVisible();

  // The consent row shows on the account page with its channel and time.
  await page.goto("/account");
  const permissions = page.getByRole("region", { name: "Who may contact you" });
  await expect(permissions.getByLabel("Email from Demo Land Co.")).toBeChecked();
  await expect(permissions).toContainText(/Allowed since \w{3} \d{1,2}, \d{4}/);

  const owner = await ownerPage(browser, view);
  await owner.goto(`/app/${DEMO_TENANT_ID}/inquiries`);
  const hold = owner.getByRole("listitem").filter({ hasText: buyerName });
  await expect(hold).toContainText(`Lot ${number}, Juniper Bench`);
  await expect(hold).toContainText("Allows: email");
  await hold.getByRole("button", { name: `Approve hold for ${buyerName}` }).click();
  await expect(hold).toContainText("Approved");
  await expect(hold).toContainText("On hold");

  await page.goto(`/juniper-bench/lots/${number}`);
  await expect(page.getByRole("heading", { level: 1, name: `Lot ${number}` })).toBeVisible();
  await expect(page.getByText("On hold", { exact: true }).first()).toBeVisible();
});

test("a status change emails each saver exactly once", async ({ page, browser }, testInfo) => {
  const view = viewport(testInfo.project.name);
  const number = ALERT_LOTS[view] ?? "3-6";
  const buyer = `buyer+${view}@buyers.cornerpin.test`;
  const subject = `Lot ${number} at Juniper Bench is now on hold`;

  await page.goto(`/juniper-bench/lots/${number}`);
  await page.getByRole("button", { name: "Save this lot" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();

  const owner = await ownerPage(browser, view);
  await owner.goto(`/app/${DEMO_TENANT_ID}`);
  await owner.getByRole("link", { name: "Juniper Bench" }).click();
  await owner.getByRole("link", { name: `Lot ${number}`, exact: true }).click();
  await owner.getByLabel("Status", { exact: true }).click();
  await owner.getByRole("option", { name: "On hold", exact: true }).click();
  await owner.getByRole("button", { name: "Save lot" }).click();
  await expect(owner.getByText("Available → On hold")).toBeVisible();

  const [mail] = await expectMail(() => mailTo(page.request, buyer, subject), 1);
  expect(mail?.text).toContain("Status: available → on hold");
  expect(mail?.text).toContain(`/juniper-bench/lots/${number}`);
});
