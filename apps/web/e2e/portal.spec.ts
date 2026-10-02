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

// P1-05 acceptance: upload, reorder and caption photos; documents download.

// A 1x1 PNG and a minimal PDF: enough for the server's checks, small enough to inline.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAEBgIApD5fRAAAAABJRU5ErkJggg==",
  "base64",
);
const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");

type SubdivisionDetail = { id: string; slug: string; phases: { id: string; name: string }[] };

async function juniperBench(page: Page): Promise<SubdivisionDetail> {
  const base = `/v1/tenants/${DEMO_TENANT_ID}`;
  const list = (await (await page.request.get(`${base}/subdivisions`)).json()) as {
    id: string;
    slug: string;
  }[];
  const juniper = list.find((s) => s.slug === "juniper-bench");
  if (!juniper) throw new Error("Juniper Bench is not seeded");
  return (await (
    await page.request.get(`${base}/subdivisions/${juniper.id}`)
  ).json()) as SubdivisionDetail;
}

/** A fresh lot in Juniper Bench for this viewport, so parallel runs never share it. */
async function newLot(page: Page, number: string, published = false): Promise<string> {
  const base = `/v1/tenants/${DEMO_TENANT_ID}`;
  const detail = await juniperBench(page);
  const phase = detail.phases[0];
  if (!phase) throw new Error("Juniper Bench has no phases");
  const created = await page.request.post(`${base}/subdivisions/${detail.id}/lots`, {
    data: { number, phase_id: phase.id, published },
  });
  expect(created.status()).toBe(201);
  return ((await created.json()) as { id: string }).id;
}

test("owner uploads, captions and reorders photos, and downloads a document", async ({
  page,
}, testInfo) => {
  page.on("dialog", (dialog) => void dialog.accept());
  const lotId = await newLot(page, `P-${viewport(testInfo.project.name)}`);
  await page.goto(`/app/${DEMO_TENANT_ID}/lots/${lotId}`);

  // Photos: two at once.
  await page.getByLabel("Add photos").setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: PNG },
    { name: "road.png", mimeType: "image/png", buffer: PNG },
  ]);
  await expect(page.getByLabel("Caption for photo 2")).toBeVisible();

  await page.getByLabel("Caption for photo 1").fill("Front of the lot");
  await page.getByLabel("Caption for photo 1").press("Enter");
  await expect(page.getByAltText("Front of the lot")).toBeVisible();
  await page.getByLabel("Caption for photo 2").fill("View from the road");
  await page.getByLabel("Caption for photo 2").press("Enter");
  await expect(page.getByAltText("View from the road")).toBeVisible();

  // Reorder: the road view goes first, and stays first after a reload.
  await page.getByRole("button", { name: "Move photo 2 earlier" }).click();
  await expect(page.getByLabel("Caption for photo 1")).toHaveValue("View from the road");
  await page.reload();
  await expect(page.getByLabel("Caption for photo 1")).toHaveValue("View from the road");
  await expect(page.getByLabel("Caption for photo 2")).toHaveValue("Front of the lot");

  // The images themselves load through the API.
  const first = page.getByAltText("View from the road");
  await expect(first).toBeVisible();
  expect(await first.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(1);

  // Documents: upload a plat and download it under its title.
  await choose(page, "Kind", "Plat");
  await page.getByLabel("Title").fill("Recorded plat");
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "scan0042.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  await page.getByRole("button", { name: "Upload document" }).click();
  await expect(page.getByText("Recorded plat", { exact: true })).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download Recorded plat" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("Recorded plat.pdf");

  // Deleting a photo takes it off the page.
  await page.getByRole("button", { name: "Delete photo 2" }).click();
  await expect(page.getByLabel("Caption for photo 2")).toHaveCount(0);
});

// P1-06 acceptance: a drawn lot round-trips through PostGIS and renders on the public map.

test("owner draws a lot on the map and it appears on the public map", async ({
  page,
}, testInfo) => {
  const number = `M-${viewport(testInfo.project.name)}`;
  const lotId = await newLot(page, number, true);
  const juniper = await juniperBench(page);

  await page.goto(`/app/${DEMO_TENANT_ID}/subdivisions/${juniper.id}/map`);
  const editor = page.getByRole("region", { name: "Map editor" });
  await expect(editor).toHaveAttribute("data-ready", "true", { timeout: 20_000 });

  await page.getByRole("button", { name: new RegExp(`Lot ${number}`) }).click();
  await expect(page.getByRole("heading", { name: `Lot ${number}` })).toBeVisible();
  await page.getByRole("button", { name: "Draw shape" }).click();

  // Four corners around the middle of the map, then Enter to close the shape.
  await editor.scrollIntoViewIfNeeded();
  const box = await editor.boundingBox();
  if (!box) throw new Error("map editor has no size");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  for (const [dx, dy] of [
    [-40, -30],
    [40, -30],
    [40, 30],
    [-40, 30],
  ] as const) {
    await page.mouse.click(cx + dx, cy + dy);
  }
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Save shape" }).click();
  await expect(page.getByText(new RegExp(`Saved lot ${number}: [0-9.]+ ac`))).toBeVisible();

  // Stored in PostGIS: the map endpoint returns it as a MultiPolygon with acreage.
  const saved = (await (
    await page.request.get(`/v1/tenants/${DEMO_TENANT_ID}/subdivisions/${juniper.id}/map`)
  ).json()) as { lots: { id: string; acreage: number | null; boundary: { type: string } | null }[] };
  const lot = saved.lots.find((candidate) => candidate.id === lotId);
  expect(lot?.boundary?.type).toBe("MultiPolygon");
  expect(lot?.acreage).toBeGreaterThan(0);

  // Rendered on the public map.
  await page.goto(`/${juniper.slug}`);
  const publicMap = page.getByRole("region", { name: "Map of lots" });
  await expect
    .poll(async () => (await publicMap.getAttribute("data-rendered-lots"))?.split(",") ?? [], {
      timeout: 20_000,
    })
    .toContain(number);
  await expect(page.getByText(`Lot ${number}`, { exact: true })).toBeVisible();
});

test("owner imports a lot shape from GeoJSON", async ({ page }, testInfo) => {
  const number = `I-${viewport(testInfo.project.name)}`;
  const lotId = await newLot(page, number);
  const juniper = await juniperBench(page);
  const mapUrl = `/v1/tenants/${DEMO_TENANT_ID}/subdivisions/${juniper.id}/map`;
  const { center } = (await (await page.request.get(mapUrl)).json()) as { center: [number, number] };
  const [lng, lat] = center;
  const ring = [
    [lng, lat],
    [lng + 0.0005, lat],
    [lng + 0.0005, lat + 0.0004],
    [lng, lat + 0.0004],
    [lng, lat],
  ];
  const geojson = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: { LOT: `Lot ${number}` }, geometry: { type: "Polygon", coordinates: [ring] } },
    ],
  };

  await page.goto(`/app/${DEMO_TENANT_ID}/subdivisions/${juniper.id}/map`);
  await page.getByLabel("GeoJSON file").setInputFiles({
    name: "lots.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(geojson)),
  });
  const row = page.getByRole("row", { name: new RegExp(number) });
  await expect(row.getByText("Update")).toBeVisible();
  await page.getByRole("button", { name: "Apply import (1)" }).click();
  await expect(page.getByText("Imported 1 shape.")).toBeVisible();

  const after = (await (await page.request.get(mapUrl)).json()) as {
    lots: { id: string; boundary: unknown }[];
  };
  expect(after.lots.find((lot) => lot.id === lotId)?.boundary).not.toBeNull();

});

test("owner adds a plat image and removes it", async ({ page }, testInfo) => {
  page.on("dialog", (dialog) => void dialog.accept());
  // A subdivision of its own: there is one plat per subdivision, and viewports run in parallel.
  const created = await page.request.post(`/v1/tenants/${DEMO_TENANT_ID}/subdivisions`, {
    data: {
      name: `Plat ${viewport(testInfo.project.name)}`,
      slug: `plat-${viewport(testInfo.project.name)}`,
      time_zone: "America/Boise",
      latitude: 43.4,
      longitude: -116.4,
    },
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };

  await page.goto(`/app/${DEMO_TENANT_ID}/subdivisions/${id}/map`);
  await expect(page.getByRole("region", { name: "Map editor" })).toHaveAttribute(
    "data-ready",
    "true",
    { timeout: 20_000 },
  );
  await page.getByLabel("Add plat image").setInputFiles({
    name: "plat.png",
    mimeType: "image/png",
    buffer: PNG,
  });
  await expect(page.getByText("Plat added.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Line up plat" })).toBeVisible();
  await expect(page.getByLabel(/See-through/)).toBeVisible();

  await page.getByRole("button", { name: "Remove plat" }).click();
  await expect(page.getByText("Plat removed.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Line up plat" })).toHaveCount(0);
});
