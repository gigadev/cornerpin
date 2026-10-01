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

test("service worker caches nothing yet", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();

  // Serwist opens an empty precache bucket on install; what matters is that nothing is in it.
  const cachedUrls = await page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys()) {
      const cache = await caches.open(name);
      urls.push(...(await cache.keys()).map((request) => request.url));
    }
    return urls;
  });
  expect(cachedUrls).toEqual([]);
});
