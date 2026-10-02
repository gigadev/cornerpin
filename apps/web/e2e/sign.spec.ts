import { expect, test, type APIRequestContext, type Locator } from "@playwright/test";
import jsQR from "jsqr";
import { PNG } from "pngjs";
import { DEMO_TENANT_ID } from "./fixtures";

// P1-11 acceptance: scanning a printed code opens the right lot after a slug rename. Runs in
// the portal projects, signed in as portal+<viewport>@demo.cornerpin.test.

const viewport = (name: string) => name.replace("-portal", "");
const base = `/v1/tenants/${DEMO_TENANT_ID}`;

async function post<T>(request: APIRequestContext, path: string, data: object): Promise<T> {
  const response = await request.post(path, { data });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as T;
}

/** Read the QR code the way a phone would: from its pixels. */
async function scan(code: Locator): Promise<string> {
  const png = PNG.sync.read(await code.screenshot());
  const result = jsQR(new Uint8ClampedArray(png.data), png.width, png.height);
  if (!result) throw new Error("no QR code found in the sign");
  return result.data;
}

test("a printed sign's code opens the right lot after a slug rename", async ({
  page,
}, testInfo) => {
  const view = viewport(testInfo.project.name);
  const slug = `sign-${view}-${Date.now()}`;
  const subdivision = await post<{ id: string }>(page.request, `${base}/subdivisions`, {
    name: `Sign Ridge ${view}`,
    slug,
    time_zone: "America/Boise",
    latitude: 43.4,
    longitude: -116.39,
    published: true,
  });
  const phase = await post<{ id: string }>(
    page.request,
    `${base}/subdivisions/${subdivision.id}/phases`,
    { name: "Phase 1" },
  );
  const lot = await post<{ id: string }>(
    page.request,
    `${base}/subdivisions/${subdivision.id}/lots`,
    { number: "S1", phase_id: phase.id, price: 99000, published: true },
  );

  await page.goto(`/app/${DEMO_TENANT_ID}/lots/${lot.id}`);
  await page.getByRole("link", { name: "Print a sign" }).click();
  await expect(page.getByRole("heading", { name: "Sign for Lot S1" })).toBeVisible();
  const sign = page.getByRole("article", { name: "Sign" });
  await expect(sign).toContainText(`Sign Ridge ${view}`);
  await expect(sign).toContainText("Lot S1");

  // Printed, the sign is all there is on the page.
  await page.emulateMedia({ media: "print" });
  await expect(page.getByRole("button", { name: "Print" })).toBeHidden();
  await expect(page.getByRole("banner")).toBeHidden();
  await expect(sign).toBeVisible();

  const scanned = await scan(sign.getByRole("img", { name: /^QR code for / }));
  expect(scanned).toMatch(/\/q\/[a-z0-9]{8}$/);
  await expect(sign).toContainText(new URL(scanned).pathname);
  // The same code every time the sign is opened.
  await page.reload();
  expect(await scan(sign.getByRole("img", { name: /^QR code for / }))).toBe(scanned);
  await page.emulateMedia({ media: "screen" });

  await page.goto(scanned);
  await expect(page).toHaveURL(new RegExp(`/${slug}/lots/S1$`));
  await expect(page.getByRole("heading", { level: 1, name: "Lot S1" })).toBeVisible();

  const renamed = `${slug}-new`;
  const patched = await page.request.patch(`${base}/subdivisions/${subdivision.id}`, {
    data: { slug: renamed },
  });
  expect(patched.ok()).toBe(true);

  await page.goto(scanned);
  await expect(page).toHaveURL(new RegExp(`/${renamed}/lots/S1$`));
  await expect(page.getByRole("heading", { level: 1, name: "Lot S1" })).toBeVisible();
  expect((await page.request.get(`/${slug}/lots/S1`)).status()).toBe(404);
});

test("a code for a lot that isn't listed says so", async ({ page }) => {
  const response = await page.goto("/q/zzzzzzzz");
  expect(response?.status()).toBe(404);
  await expect(
    page.getByRole("heading", { name: "This lot isn't listed right now" }),
  ).toBeVisible();
});
