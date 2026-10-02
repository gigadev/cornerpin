import { expect, test } from "@playwright/test";
import { API_URL } from "./fixtures";

// P1-07 acceptance: public pages render without JavaScript; unpublished lots never appear.
// The e2e seed gives Juniper Bench lot 7 (a published lot + home) two photos and a plat, and
// lot 16 (phase 2, unpublished) a photo.

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("subdivision page lists lots and filters them", async ({ page }) => {
    await page.goto("/juniper-bench");
    await expect(page.getByRole("heading", { level: 1, name: "Juniper Bench" })).toBeVisible();
    await expect(page.getByRole("status")).toHaveText("15 lots");
    // A browser with JavaScript off shows the <noscript> note in place of the map. Playwright
    // only stops scripts from running; its parser still treats <noscript> as scripting-on and
    // never displays it, so check that the server sends it.
    expect(await page.content()).toMatch(/<noscript>.*The map needs JavaScript\./);
    const list = page.getByRole("region", { name: "Lots" }).getByRole("listitem");
    await expect(list).toHaveCount(15);

    // The filter form is a plain GET form.
    await page.getByLabel("Status").selectOption("sold");
    await page.getByRole("button", { name: "Show lots" }).click();
    await expect(page).toHaveURL(/status=sold/);
    await expect(page.getByRole("status")).toHaveText("Showing 3 of 15 lots");
    await expect(list).toHaveCount(3);
    for (const item of await list.all()) await expect(item).toContainText("Sold");

    await page.getByLabel("Status").selectOption("available");
    await page.getByLabel("Listing").selectOption("lot_and_home");
    await page.getByRole("button", { name: "Show lots" }).click();
    await expect(page.getByRole("status")).toHaveText("Showing 2 of 15 lots");

    await page.getByRole("link", { name: "Clear" }).click();
    await expect(page.getByRole("status")).toHaveText("15 lots");
  });

  test("lot page shows price, status, photos, documents and directions", async ({
    page,
    request,
  }) => {
    await page.goto("/juniper-bench");
    await page.getByRole("link", { name: /^Lot 7\b/ }).click();
    await expect(page).toHaveURL(/\/juniper-bench\/lots\/7$/);

    await expect(page.getByRole("heading", { level: 1, name: "Lot 7" })).toBeVisible();
    await expect(page.getByText("$549,000")).toBeVisible();
    await expect(page.getByText("Available", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("4 bed · 3 bath · 2,650 sq ft")).toBeVisible();

    // Photos: in the owner's order, served (optimised) without JavaScript.
    const cover = page.getByRole("img", { name: "Front of the house" });
    await expect(cover).toBeVisible();
    await expect(page.getByRole("img", { name: "Back porch" })).toBeVisible();
    const src = await cover.getAttribute("src");
    expect(src).toBeTruthy();
    const image = await request.get(src ?? "");
    expect(image.ok()).toBe(true);
    expect(image.headers()["content-type"]).toMatch(/^image\//);

    // Documents download under their title.
    const plat = page.getByRole("link", { name: "Recorded plat" });
    const file = await request.get((await plat.getAttribute("href")) ?? "");
    expect(file.headers()["content-type"]).toBe("application/pdf");
    expect(file.headers()["content-disposition"]).toContain('filename="Recorded plat.pdf"');

    const directions = await page.getByRole("link", { name: "Directions" }).getAttribute("href");
    expect(directions).toMatch(/^https:\/\/www\.google\.com\/maps\/dir\/\?api=1&destination=43\.\d+%2C-116\.\d+$/);
  });

  test("unpublished lots never appear", async ({ page, request }) => {
    await page.goto("/juniper-bench");
    await expect(page.getByRole("link", { name: /^Lot 16\b/ })).toHaveCount(0);

    const response = await page.goto("/juniper-bench/lots/16");
    expect(response?.status()).toBe(404);
    await expect(page.getByText("Not yet public")).toHaveCount(0);

    // And the public API says it doesn't exist.
    const graphql = await request.post(`${API_URL}/graphql`, {
      data: { query: '{ lot(subdivisionSlug: "juniper-bench", number: "16") { number } }' },
    });
    expect(await graphql.json()).toEqual({ data: { lot: null } });
  });

  test("link previews", async ({ page, request }) => {
    for (const [path, title] of [
      ["/juniper-bench", "Juniper Bench"],
      ["/juniper-bench/lots/7", "Lot 7, Juniper Bench"],
    ] as const) {
      await page.goto(path);
      await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", title);
      const description = await page.locator('meta[property="og:description"]').getAttribute("content");
      expect(description).toBeTruthy();
      const image = await page.locator('meta[property="og:image"]').getAttribute("content");
      expect(image).toMatch(/^http:\/\/localhost:3100\//);
      const card = await request.get(image ?? "");
      expect(card.headers()["content-type"]).toBe("image/png");
      await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute(
        "content",
        "summary_large_image",
      );
    }
  });
});

test("lot page map frames the lot (with JavaScript)", async ({ page }) => {
  await page.goto("/juniper-bench/lots/7");
  const map = page.getByRole("region", { name: "Map of lots" });
  await expect
    .poll(async () => (await map.getAttribute("data-rendered-lots"))?.split(",") ?? [], {
      timeout: 20_000,
    })
    .toContain("7");
});
