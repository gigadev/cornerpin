import { expect, test, type Browser, type Page } from "@playwright/test";
import { DEMO_LOTS, DEMO_TENANT_ID, lotRow } from "./fixtures";

const { home, otherHome, unopened } = DEMO_LOTS;

// P1-10 acceptance: installable; a viewed lot opens offline; no /app response in any cache.
// Runs in the buyer projects (signed in as buyer+<viewport>@buyers.cornerpin.test), against
// the production build, where the service worker runs.

const viewport = (name: string) => name.replace("-buyer", "");

async function freshPage(browser: Browser, storageState?: string): Promise<Page> {
  const context = await browser.newContext({
    storageState: storageState ?? { cookies: [], origins: [] },
  });
  return context.newPage();
}

/** Wait until the service worker controls the page and has kept `path`. (waitForFunction
 * doesn't await an async predicate, so this polls instead.) */
async function waitUntilKept(page: Page, path: string): Promise<void> {
  await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await expect
    .poll(
      () =>
        page.evaluate(
          async (url) => (await (await caches.open("pages")).match(url)) !== undefined,
          path,
        ),
      { timeout: 15_000 },
    )
    .toBe(true);
}

async function cachedUrls(page: Page): Promise<string[]> {
  return page.evaluate(async () => {
    const urls: string[] = [];
    for (const name of await caches.keys()) {
      for (const request of await (await caches.open(name)).keys()) urls.push(request.url);
    }
    return urls;
  });
}

test("each subdivision and the owner portal install as their own app", async ({ page }) => {
  await page.goto(`/juniper-bench/lots/${home}`);
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    "href",
    "/juniper-bench/manifest.webmanifest",
  );
  const response = await page.request.get("/juniper-bench/manifest.webmanifest");
  const manifest = (await response.json()) as {
    name: string;
    start_url: string;
    scope: string;
    display: string;
  };
  expect(manifest).toMatchObject({
    name: "Juniper Bench · Cornerpin",
    start_url: "/juniper-bench",
    scope: "/juniper-bench",
    display: "standalone",
  });
  expect((await page.request.get("/no-such-place/manifest.webmanifest")).status()).toBe(404);

  await page.goto("/");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute(
    "href",
    "/manifest.webmanifest",
  );
  const portal = (await (await page.request.get("/app/manifest.webmanifest")).json()) as {
    scope: string;
  };
  expect(portal.scope).toBe("/app");
});

test("a viewed lot opens offline, with its subdivision", async ({ browser }) => {
  const page = await freshPage(browser);
  await page.goto(`/juniper-bench/lots/${home}`);
  await expect(page.getByRole("heading", { level: 1, name: `Lot ${home}` })).toBeVisible();
  await waitUntilKept(page, `/juniper-bench/lots/${home}`);
  await waitUntilKept(page, "/juniper-bench");

  await page.context().setOffline(true);
  await page.goto(`/juniper-bench/lots/${home}`);
  await expect(page.getByRole("heading", { level: 1, name: `Lot ${home}` })).toBeVisible();
  await expect(page.getByText("$549,000")).toBeVisible();

  await page.goto("/juniper-bench");
  const lots = page.getByRole("region", { name: "Lots" });
  await expect(lots.getByRole("link", { name: lotRow(home) })).toBeVisible();
  await expect(lots.getByRole("link", { name: lotRow(unopened) })).toBeVisible();

  // A lot that was never opened gets the offline page, which lists what this device has.
  await page.goto(`/juniper-bench/lots/${unopened}`);
  await expect(page.getByRole("heading", { name: "You're offline" })).toBeVisible();
  await expect(page.getByRole("link", { name: `Lot ${home}, Juniper Bench` })).toBeVisible();
  await expect(page.getByRole("link", { name: "Juniper Bench", exact: true })).toBeVisible();
});

test("a question written offline is sent when the connection returns", async ({
  browser,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const question = `Can I walk the lot this weekend? (${view} ${Date.now()})`;
  const page = await freshPage(browser);
  await page.goto(`/juniper-bench/lots/${home}`);
  // The form is ready once Cloudflare's test key has passed.
  await expect(page.getByRole("button", { name: "Send question" })).toBeEnabled({
    timeout: 15_000,
  });

  await page.context().setOffline(true);
  await page.getByLabel("Your name").fill("Offline Visitor");
  await page.getByLabel("Email").fill(`offline+${view}@example.test`);
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByText("Your question is saved on this device")).toBeVisible();
  await expect(
    page.getByText(
      `Your question about Lot ${home}, Juniper Bench will be sent when you're back online`,
    ),
  ).toBeVisible();

  await page.context().setOffline(false);
  await expect(page.getByText(`Sent your question about Lot ${home}, Juniper Bench.`)).toBeVisible({
    timeout: 20_000,
  });

  const owner = await freshPage(browser, `playwright/.auth/portal-${view}.json`);
  await owner.goto(`/app/${DEMO_TENANT_ID}/inquiries`);
  await expect(owner.getByRole("listitem").filter({ hasText: question })).toContainText(
    `offline+${view}@example.test`,
  );
});

test("nothing private is ever cached", async ({ page, browser }, testInfo) => {
  test.setTimeout(60_000);
  const view = viewport(testInfo.project.name);
  // The buyer's own pages and data, through the worker.
  await page.goto(`/juniper-bench/lots/${home}`);
  await waitUntilKept(page, `/juniper-bench/lots/${home}`);
  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Your account" })).toBeVisible();
  await page.goto(`/juniper-bench/lots/${otherHome}`);
  await expect(page.getByRole("button", { name: /Save this lot|Saved/ })).toBeVisible();

  // The owner portal, in a session that has the worker too.
  const owner = await freshPage(browser, `playwright/.auth/portal-${view}.json`);
  await owner.goto("/juniper-bench");
  await owner.waitForFunction(() => navigator.serviceWorker.controller !== null);
  for (const path of ["/account", "/app", `/app/${DEMO_TENANT_ID}`]) {
    await owner.goto(path);
  }
  // Client-side navigation too, which the page cacher sees.
  await owner.goto(`/app/${DEMO_TENANT_ID}/inquiries`);
  await owner.getByRole("link", { name: "Organizations" }).click();
  await owner.getByRole("link", { name: "Demo Land Co." }).click();
  await owner.getByRole("link", { name: "Juniper Bench" }).click();
  await expect(owner.getByRole("link", { name: "New lot" })).toBeVisible();

  const origin = new URL(page.url()).origin;
  const kept = [...(await cachedUrls(page)), ...(await cachedUrls(owner))]
    .filter((url) => url.startsWith(origin))
    .map((url) => new URL(url).pathname);
  expect(kept).toContain(`/juniper-bench/lots/${home}`);
  const privatePaths = kept.filter(
    (path) =>
      /^\/(app|account|signin|auth|graphql)(\/|$)/.test(path) ||
      (path.startsWith("/v1/") && !path.startsWith("/v1/public/photos/")),
  );
  expect(privatePaths).toEqual([]);
});
