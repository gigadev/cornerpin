import { expect, test, type Page } from "@playwright/test";
import { DEMO_TENANT_ID, OTHER_TENANT_ID } from "./fixtures";

// P1-04 acceptance: create a lot, change its status, see the history. Plus a smoke test for
// each portal screen. Runs signed in as portal+<viewport>@demo.cornerpin.test.

const viewport = (name: string) => name.replace("-portal", "");

async function choose(page: Page, label: string, option: string) {
  await page.getByLabel(label, { exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

test("owner creates a lot, changes its status and price, and sees the history", async ({
  page,
}, testInfo) => {
  const owner = `portal+${viewport(testInfo.project.name)}@demo.cornerpin.test`;
  const number = `E2E-${viewport(testInfo.project.name)}`;

  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: "Juniper Bench" }).click();
  await page.getByRole("link", { name: "New lot" }).click();
  await expect(page.getByRole("heading", { name: "New lot" })).toBeVisible();

  await page.getByLabel("Lot number").fill(number);
  await choose(page, "Phase", "Phase 1");
  await page.getByLabel("Price (whole dollars)").fill("$99,000");
  await page.getByLabel("Acreage").fill("1.1");
  await page.getByRole("button", { name: "Create lot" }).click();

  await expect(page.getByRole("heading", { name: `Lot ${number}` })).toBeVisible();
  const history = page.getByRole("region", { name: "Status changes" });
  await expect(history.getByText("Listed as Available")).toBeVisible();
  await expect(page.getByText("Priced at $99,000")).toBeVisible();

  await choose(page, "Status", "On hold");
  await page.getByLabel("Price (whole dollars)").fill("97500");
  await page.getByRole("button", { name: "Save lot" }).click();

  await expect(history.getByText("Available → On hold")).toBeVisible();
  await expect(history.getByText(owner).first()).toBeVisible();
  await expect(page.getByText("$99,000 → $97,500")).toBeVisible();

  // The new lot shows on the subdivision page with its new status.
  await page.getByRole("link", { name: "Juniper Bench" }).click();
  const row = page.getByRole("row", { name: new RegExp(`Lot ${number}`) });
  await expect(row.getByText("On hold")).toBeVisible();
});

test("owner creates a subdivision with a phase, then deletes it", async ({ page }, testInfo) => {
  const name = `E2E ${viewport(testInfo.project.name)} Ridge`;
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: "New subdivision" }).click();
  await page.getByLabel("Name").fill(name);
  await expect(page.getByLabel("Web address")).toHaveValue(
    `e2e-${viewport(testInfo.project.name)}-ridge`,
  );
  await page.getByLabel("Latitude").fill("47.69");
  await page.getByLabel("Longitude").fill("-116.78");
  await choose(page, "Time zone", "Pacific: northern Idaho (America/Los_Angeles)");
  await page.getByRole("button", { name: "Create subdivision" }).click();

  await expect(page.getByRole("heading", { name })).toBeVisible();
  await expect(page.getByText("Add a phase first")).toBeVisible();

  await page.getByLabel("New phase").fill("Phase 1");
  await page.getByRole("button", { name: "Add phase" }).click();
  await expect(page.getByLabel("Name of Phase 1")).toBeVisible();
  await expect(page.getByRole("link", { name: "New lot" })).toBeVisible();

  await page.getByRole("button", { name: "Delete subdivision" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/${DEMO_TENANT_ID}$`));
  await expect(page.getByRole("link", { name })).toHaveCount(0);
});

test("a duplicate web address is explained, not lost", async ({ page }) => {
  await page.goto(`/app/${DEMO_TENANT_ID}/subdivisions/new`);
  await page.getByLabel("Name").fill("Juniper Bench");
  await page.getByLabel("Latitude").fill("43.4");
  await page.getByLabel("Longitude").fill("-116.4");
  await page.getByRole("button", { name: "Create subdivision" }).click();
  await expect(page.getByText("That web address is already taken")).toBeVisible();
  await expect(page.getByLabel("Name")).toHaveValue("Juniper Bench");
});

test("other tenants' and unknown records are not found", async ({ page }) => {
  const missing = "00000000-0000-4000-8000-000000000000";
  for (const path of [
    `/app/${OTHER_TENANT_ID}/subdivisions/new`,
    `/app/${DEMO_TENANT_ID}/subdivisions/${missing}`,
    `/app/${DEMO_TENANT_ID}/lots/${missing}`,
    `/app/${DEMO_TENANT_ID}/lots/not-a-uuid`,
  ]) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(404);
  }
});
