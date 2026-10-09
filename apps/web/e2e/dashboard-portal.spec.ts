import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";
import type { components } from "../lib/api/schema";
import { clearInbox, DEMO_LOTS, DEMO_TENANT_ID, OTHER_TENANT_ID, signInLink } from "./fixtures";

// P3-07 acceptance (ADR-051): the demo dashboard shows each figure, and they match the tables;
// a tenant with no leads renders empty states, not errors. pytest checks the API's figures
// against the raw tables; this checks the page shows exactly what the API says. Other tests add
// leads and holds at the same time, so the comparison retries until it sees one snapshot.

type Dashboard = components["schemas"]["Dashboard"];
const viewport = (name: string) => name.replace("-portal", "");
const STAGES: Record<string, string> = {
  new: "New",
  contacted: "Contacted",
  engaged: "Engaged",
  holding: "Holding",
  won: "Won",
};

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

function tile(page: Page, label: string) {
  return page.getByText(label, { exact: true }).locator("..");
}

test("the dashboard shows exactly the figures the API computes from the tables", async ({
  page,
  browser,
}, testInfo) => {
  // At least one lead, so the funnel has figures even when this spec runs on its own.
  const visitor = await (
    await browser.newContext({ storageState: { cookies: [], origins: [] } })
  ).newPage();
  await visitor.goto(`/juniper-bench/lots/${DEMO_LOTS.otherHome}`);
  const send = visitor.getByRole("button", { name: "Send question" });
  await expect(send).toBeEnabled({ timeout: 15_000 });
  await visitor.getByLabel("Your name").fill("Dana Dashboard");
  await visitor
    .getByLabel("Email")
    .fill(`dashboard+${viewport(testInfo.project.name)}-${Date.now()}@example.test`);
  await visitor.getByLabel("Your question").fill("How big is the lot?");
  await send.click();
  await expect(visitor.getByRole("status")).toContainText("Sent.");

  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await expect(async () => {
    await page.reload();
    const response = await page.request.get(`/v1/tenants/${DEMO_TENANT_ID}/dashboard`);
    const board = (await response.json()) as Dashboard;

    await expect(tile(page, "Leads")).toContainText(String(board.leads), { timeout: 1_000 });
    const won = board.funnel.find((stage) => stage.stage === "won")?.reached ?? 0;
    await expect(tile(page, "Won")).toContainText(String(won), { timeout: 1_000 });
    const sold = board.sales_by_month.reduce((total, month) => total + month.sold, 0);
    await expect(tile(page, "Lots sold")).toContainText(String(sold), { timeout: 1_000 });
    await expect(tile(page, "Messages sent")).toContainText(String(board.outreach.sent), {
      timeout: 1_000,
    });

    const funnel = page.getByRole("region", { name: "Lead funnel" });
    for (const stage of board.funnel.filter((s) => s.stage !== "lost")) {
      await expect(funnel).toContainText(`${STAGES[stage.stage]}: ${stage.reached} reached`, {
        timeout: 1_000,
      });
    }

    const inventory = page.getByRole("region", { name: "Lots by phase" });
    for (const phase of board.inventory) {
      const name = `${phase.subdivision_name}, ${phase.phase_name}`;
      const row = inventory.getByRole("row").filter({ has: page.getByRole("cell", { name, exact: true }) });
      await expect(row.getByRole("cell")).toHaveText(
        [`${phase.subdivision_name}, ${phase.phase_name}`, String(phase.available), String(phase.on_hold), String(phase.sold)],
        { timeout: 1_000 },
      );
    }

    const sales = page.getByRole("region", { name: "Lots sold each month" });
    await sales.getByText("As a table").click();
    const months = sales.getByRole("row");
    await expect(months).toHaveCount(board.sales_by_month.length + 1, { timeout: 1_000 });
    const cells = await sales.getByRole("cell").allTextContents();
    const shown = cells.filter((_, i) => i % 2 === 1).map(Number);
    expect(shown).toEqual(board.sales_by_month.map((month) => month.sold));

    const pace = page.getByRole("region", { name: "From listing to sold" });
    for (const phase of board.days_to_sold) {
      const name = `${phase.subdivision_name}, ${phase.phase_name}`;
      const row = pace.getByRole("row").filter({ has: page.getByRole("cell", { name, exact: true }) });
      await expect(row).toContainText(
        String(phase.sold),
        { timeout: 1_000 },
      );
    }

    const outreach = page.getByRole("region", { name: "Outreach" });
    await expect(outreach).toContainText(`Replies${board.outreach.replied}`, { timeout: 1_000 });
    await expect(outreach).toContainText(`Handed to a person${board.outreach.handed_off}`, {
      timeout: 1_000,
    });
  }).toPass({ timeout: 30_000 });
});

test("a tenant with nothing yet sees empty states, not errors", async ({ browser, request }, testInfo) => {
  const owner = await signedIn(
    browser,
    request,
    `dashboard+${viewport(testInfo.project.name)}@other.cornerpin.test`,
  );
  await owner.goto(`/app/${OTHER_TENANT_ID}/dashboard`);
  await expect(owner.getByRole("heading", { level: 1, name: "Dashboard" })).toBeVisible();
  await expect(tile(owner, "Leads")).toContainText("0");
  await expect(owner.getByRole("region", { name: "Lead funnel" })).toContainText(
    "No leads yet. A lead appears when someone asks about a lot.",
  );
  await expect(owner.getByRole("region", { name: "Lots sold each month" })).toContainText(
    "No lots sold in the last 12 months.",
  );
  await expect(owner.getByRole("region", { name: "Lots by phase" })).toContainText("No lots yet.");
  await expect(owner.getByRole("region", { name: "Open leads by risk" })).toContainText(
    "No open leads to score.",
  );
});
