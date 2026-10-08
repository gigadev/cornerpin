import { expect, test } from "@playwright/test";

// P1-01 acceptance: the web shell renders at 390 px and 1280 px (one project each) with a
// valid manifest and a registered service worker.

test("shell renders without horizontal scroll", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Cornerpin", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
});

test("manifest is linked, parses and its icons load", async ({ page, request }) => {
  await page.goto("/");

  const href = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(href).toBeTruthy();

  const response = await request.get(href ?? "");
  expect(response.ok()).toBe(true);
  const manifest = (await response.json()) as {
    name?: string;
    start_url?: string;
    display?: string;
    icons?: { src: string; sizes: string; type: string }[];
  };
  expect(manifest.name).toBe("Cornerpin");
  expect(manifest.start_url).toBe("/");
  expect(manifest.display).toBe("standalone");

  for (const icon of manifest.icons ?? []) {
    const image = await request.get(icon.src);
    expect(image.ok(), icon.src).toBe(true);
    expect(image.headers()["content-type"]).toContain("image/png");
  }
});

test("service worker registers at the root scope", async ({ page }) => {
  await page.goto("/");

  const scope = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return new URL(registration.scope).pathname;
  });
  expect(scope).toBe("/");
});

test("service worker precaches the offline page but not the home page", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();

  // The home page reads the session (signed in or not), so it is never kept (ADR-030).
  const cachedPaths = await page.evaluate(async () => {
    const paths: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      paths.push(...(await cache.keys()).map((request) => new URL(request.url).pathname));
    }
    return paths;
  });
  expect(cachedPaths).toContain("/offline");
  expect(cachedPaths).not.toContain("/");
});

test("the guide is a click away from sign-in and from every page's header", async ({ page }) => {
  await page.goto("/signin");
  await page.getByRole("link", { name: "See how Cornerpin works" }).click();
  await expect(page).toHaveURL(/\/help$/);
  await expect(page.getByRole("heading", { level: 1, name: "How Cornerpin works" })).toBeVisible();

  // Screenshots load (through the image optimiser) as they scroll into view.
  const first = page.getByRole("img", { name: /subdivision page with its map/ });
  await first.scrollIntoViewIfNeeded();
  await expect
    .poll(() => first.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth))
    .toBeGreaterThan(0);

  await page.goto("/juniper-bench/lots/2-5");
  await page.getByRole("banner").getByRole("link", { name: "Help" }).click();
  await expect(page).toHaveURL(/\/help$/);
  await page.getByRole("link", { name: "For owners" }).click();
  await expect(page.getByRole("heading", { name: "For owners" })).toBeInViewport();
});

test("how it's built is public and a click away from the guide", async ({ page }) => {
  await page.goto("/help");
  await page.getByRole("link", { name: "See how Cornerpin is built" }).click();
  await expect(page).toHaveURL(/\/about$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "How Cornerpin is built" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "The services it runs on" })).toBeVisible();
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(page.viewportSize()?.width ?? width);
});
