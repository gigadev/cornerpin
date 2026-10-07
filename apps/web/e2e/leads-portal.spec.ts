import { expect, test, type Page } from "@playwright/test";
import { DEMO_LOTS, DEMO_TENANT_ID } from "./fixtures";

// P2-02 acceptance: an inquiry appears as a lead; the owner changes its stage and sees it on the
// timeline. Runs signed in as portal+<viewport>@demo.cornerpin.test; the visitor is signed out.

const viewport = (name: string) => name.replace("-portal", "");

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
