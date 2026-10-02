import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  expect,
  test,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import { PNG } from "pngjs";
import { DEMO_TENANT_ID, clearInbox, signInLink } from "../e2e/fixtures";

// Takes the screenshots in public/walkthrough/, used by the in-app guide (/help) and by
// docs/WALKTHROUGH.md, and records their sizes in lib/walkthrough-shots.json. Run with
// `pnpm --filter web walkthrough`; it uses the Playwright stack, so the dev database is never
// touched. The order here sets up data first; the guides tell the story in their own order.

const OUT = path.resolve(import.meta.dirname, "../public/walkthrough");
const SIZES = path.resolve(import.meta.dirname, "../lib/walkthrough-shots.json");
// Cloudflare's test widget labels itself "For testing only" in red; production has the real
// one, so the screenshots leave it out.
const HIDE_TEST_TURNSTILE = '[data-slot="turnstile"] { visibility: hidden; }';
const MAILPIT = "http://localhost:8025";
const OWNER = "owner@demo.cornerpin.test";
const BUYER = "pat@buyers.cornerpin.test";
const DESKTOP = { width: 1280, height: 800 };
const MOBILE = { width: 390, height: 844 };

async function shot(page: Page, name: string, fullPage = false): Promise<void> {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage, animations: "disabled" });
}

/** A simple landscape: sky, distant hills, a field, and (optionally) a house. */
function scene(sky: [number, number, number], field: [number, number, number], house: boolean) {
  const width = 960;
  const height = 640;
  const png = new PNG({ width, height });
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const hill = height * 0.52 + Math.sin(x / 90) * 18 + Math.sin(x / 37) * 6;
      let color: [number, number, number];
      if (y < hill) {
        const t = y / hill;
        color = [sky[0] + t * 40, sky[1] + t * 30, sky[2] - t * 10];
      } else if (y < hill + 22) {
        color = [96, 112, 92];
      } else {
        const stripe = Math.floor((x + y * 1.6) / 28) % 2 === 0 ? 0 : 10;
        color = [field[0] + stripe, field[1] + stripe, field[2] + stripe];
      }
      const inHouse = house && x > 560 && x < 800 && y > 330 && y < 470;
      const roofTop = 250 + Math.abs(x - 680) * 0.66;
      const inRoof = house && x > 540 && x < 820 && y > roofTop && y <= 330;
      if (inRoof) color = [92, 64, 52];
      else if (inHouse) color = (x > 650 && x < 700 && y > 400) ? [70, 50, 40] : [214, 204, 186];
      const i = (y * width + x) * 4;
      png.data[i] = Math.min(255, color[0]);
      png.data[i + 1] = Math.min(255, color[1]);
      png.data[i + 2] = Math.min(255, color[2]);
      png.data[i + 3] = 255;
    }
  }
  return PNG.sync.write(png);
}

const PDF = Buffer.from("%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n");

async function newContext(browser: Browser, viewport = DESKTOP): Promise<BrowserContext> {
  return browser.newContext({ viewport, storageState: { cookies: [], origins: [] } });
}

/** Sign in through the API and the emailed link (the UI version is captured once, below). */
async function signIn(page: Page, request: APIRequestContext, email: string): Promise<void> {
  await clearInbox(request, email);
  const requested = await page.request.post("/v1/auth/magic-link", {
    data: { email, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/" },
  });
  expect(requested.status()).toBe(202);
  const token = new URL(await signInLink(request, email)).searchParams.get("token");
  const verified = await page.request.post("/v1/auth/magic-link/verify", { data: { token } });
  expect(verified.ok()).toBe(true);
}

/** The newest Mailpit message to `email` whose subject contains `subject`. */
async function mailId(request: APIRequestContext, email: string, subject: string): Promise<string> {
  let id: string | undefined;
  await expect
    .poll(
      async () => {
        const response = await request.get(`${MAILPIT}/api/v1/search`, {
          params: { query: `to:"${email}" subject:"${subject}"`, limit: "1" },
        });
        id = ((await response.json()) as { messages: { ID: string }[] }).messages[0]?.ID;
        return id;
      },
      { timeout: 20_000 },
    )
    .toBeTruthy();
  return id ?? "";
}

async function mailShot(page: Page, request: APIRequestContext, email: string, subject: string, name: string) {
  await page.goto(`${MAILPIT}/view/${await mailId(request, email, subject)}`);
  await page.waitForTimeout(800);
  await shot(page, name);
}

async function mapReady(page: Page): Promise<void> {
  await expect(page.getByRole("region", { name: "Map of lots" })).toHaveAttribute(
    "data-rendered-lots",
    /\d/,
    { timeout: 30_000 },
  );
  await page.waitForTimeout(2_000); // let the base map's tiles finish drawing
}

test("walkthrough screenshots", async ({ browser, request }) => {
  test.setTimeout(600_000);
  mkdirSync(OUT, { recursive: true });

  // --- the owner adds photos and a plat to lot 8 ---------------------------------------
  const ownerContext = await newContext(browser);
  const owner = await ownerContext.newPage();
  owner.on("dialog", (dialog) => void dialog.accept());
  await signIn(owner, request, OWNER);

  await owner.goto("/app");
  await shot(owner, "20-portal-organizations");
  await owner.getByRole("link", { name: "Demo Land Co." }).click();
  await expect(owner.getByRole("heading", { name: "Demo Land Co." })).toBeVisible();
  await shot(owner, "21-portal-tenant");
  await owner.getByRole("link", { name: "Juniper Bench" }).click();
  await expect(owner.getByRole("link", { name: "New lot" })).toBeVisible();
  await shot(owner, "22-portal-subdivision", true);
  const subdivisionUrl = owner.url();

  await owner.getByRole("link", { name: "New lot" }).click();
  await expect(owner.getByRole("heading", { name: "New lot" })).toBeVisible();
  await shot(owner, "23-portal-new-lot");

  await owner.goto(subdivisionUrl);
  await owner.getByRole("link", { name: "Lot 8", exact: true }).click();
  await expect(owner.getByRole("heading", { name: "Lot 8" })).toBeVisible();
  const lot8Url = owner.url();
  await owner.getByLabel("Add photos").setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: scene([118, 166, 214], [150, 160, 92], true) },
    { name: "lot.png", mimeType: "image/png", buffer: scene([150, 182, 220], [176, 168, 104], false) },
    { name: "evening.png", mimeType: "image/png", buffer: scene([214, 150, 118], [128, 138, 82], true) },
  ]);
  await expect(owner.getByLabel("Caption for photo 3")).toBeVisible({ timeout: 20_000 });
  for (const [index, caption] of ["Front of the house", "The back acre", "Evening light"].entries()) {
    const field = owner.getByLabel(`Caption for photo ${index + 1}`);
    await field.fill(caption);
    await field.press("Enter");
    await expect(owner.getByAltText(caption)).toBeVisible();
  }
  await owner.getByLabel("Kind").click();
  await owner.getByRole("option", { name: "Plat", exact: true }).click();
  await owner.getByLabel("Title").fill("Recorded plat");
  await owner.getByLabel("File", { exact: true }).setInputFiles({
    name: "plat.pdf",
    mimeType: "application/pdf",
    buffer: PDF,
  });
  await owner.getByRole("button", { name: "Upload document" }).click();
  await expect(owner.getByText("Recorded plat", { exact: true })).toBeVisible();
  await owner.reload();
  await shot(owner, "24-portal-lot", true);

  await owner.goto(subdivisionUrl);
  await owner.getByRole("link", { name: /Map and lot shapes/ }).click();
  await owner.waitForTimeout(5_000);
  await shot(owner, "25-portal-map-editor");

  // --- the public site, signed out ------------------------------------------------------
  const visitorContext = await newContext(browser);
  const visitor = await visitorContext.newPage();
  await visitor.goto("/");
  await shot(visitor, "01-home");
  await visitor.goto("/juniper-bench");
  await mapReady(visitor);
  await shot(visitor, "02-subdivision");
  await shot(visitor, "03-subdivision-full", true);
  await visitor.goto("/juniper-bench?status=available&listing=lot_and_home");
  await mapReady(visitor);
  await visitor.getByRole("region", { name: "Lots", exact: true }).scrollIntoViewIfNeeded();
  await shot(visitor, "04-filters");

  await visitor.goto("/juniper-bench/lots/8");
  await expect(visitor.getByRole("heading", { level: 1, name: "Lot 8" })).toBeVisible();
  await shot(visitor, "05-lot");
  await mapReady(visitor);
  await shot(visitor, "06-lot-full", true);
  await expect(visitor.getByRole("button", { name: "Send question" })).toBeEnabled({ timeout: 20_000 });
  await visitor.getByLabel("Your name").fill("Jordan Walk-in");
  await visitor.getByLabel("Email").fill("jordan@example.test");
  await visitor.getByLabel("Your question").fill("Is the well shared with lot 7?");
  await visitor.locator("#contact").scrollIntoViewIfNeeded();
  await visitor.getByRole("heading", { name: "Contact the owner" }).click();
  await visitor.addStyleTag({ content: HIDE_TEST_TURNSTILE });
  await shot(visitor, "07-contact-signed-out");
  await visitor.getByRole("button", { name: "Send question" }).click();
  await expect(visitor.getByRole("status").filter({ hasText: "Sent." })).toBeVisible();

  const card = await request.get("/juniper-bench/lots/8/opengraph-image");
  writeFileSync(path.join(OUT, "08-link-preview.png"), await card.body());

  await visitor.goto("/q/zzzzzzzz");
  await shot(visitor, "09-qr-not-listed");

  const phone = await (await newContext(browser, MOBILE)).newPage();
  await phone.goto("/juniper-bench");
  await mapReady(phone);
  await shot(phone, "10-mobile-subdivision");
  await phone.goto("/juniper-bench/lots/8");
  await expect(phone.getByRole("heading", { level: 1, name: "Lot 8" })).toBeVisible();
  await phone.waitForTimeout(1_500);
  await shot(phone, "11-mobile-lot");

  // --- a buyer signs up from a lot page ------------------------------------------------------
  await clearInbox(request, BUYER);
  const buyerContext = await newContext(browser);
  const buyer = await buyerContext.newPage();
  await buyer.goto("/juniper-bench/lots/8");
  await buyer.getByRole("link", { name: "Save this lot" }).click();
  await buyer.getByLabel("Email").fill(BUYER);
  const send = buyer.getByRole("button", { name: "Email me a sign-in link" });
  await expect(send).toBeEnabled({ timeout: 20_000 });
  await buyer.addStyleTag({ content: HIDE_TEST_TURNSTILE });
  await shot(buyer, "12-sign-in");
  await send.click();
  await expect(buyer.getByRole("status")).toContainText("Check your email");
  await shot(buyer, "13-check-email");
  const mail = await (await newContext(browser)).newPage();
  await mailShot(mail, request, BUYER, "sign-in link", "14-sign-in-email");
  await buyer.goto(await signInLink(request, BUYER));
  await shot(buyer, "15-verify");
  await buyer.getByRole("button", { name: "Sign in" }).click();
  await expect(buyer).toHaveURL(/\/juniper-bench\/lots\/8$/);

  await buyer.getByRole("button", { name: "Save this lot" }).click();
  await expect(buyer.getByRole("button", { name: "Saved" })).toBeVisible();
  await buyer.getByLabel("Your name").fill("Pat Buyer");
  await buyer.getByLabel("Phone (optional)").fill("208-555-0142");
  await buyer.getByLabel("Your question").fill("Could we walk the lot on Saturday?");
  await buyer.getByLabel("Email me about their lots").click();
  await buyer.locator("#contact").scrollIntoViewIfNeeded();
  await shot(buyer, "16-contact-signed-in");
  await buyer.getByRole("button", { name: "Send question" }).click();
  await expect(buyer.getByRole("status").filter({ hasText: "Sent." })).toBeVisible();

  await buyer.goto("/juniper-bench/lots/12");
  await buyer.getByLabel("Ask the owner to hold this lot").check();
  await buyer.getByLabel("Message (optional)").fill("Our loan is approved; can you hold it until Friday?");
  await buyer.locator("#contact").scrollIntoViewIfNeeded();
  await shot(buyer, "17-hold-request");
  await buyer.getByRole("button", { name: "Request a hold" }).click();
  await expect(buyer.getByText("Hold requested.")).toBeVisible();

  // --- the owner hears about it ------------------------------------------------------------
  await mailShot(mail, request, OWNER, "New question about Lot 8", "30-email-owner-question");
  await owner.goto(`/app/${DEMO_TENANT_ID}/inquiries`);
  await shot(owner, "26-portal-inquiries", true);

  // A price change emails the buyer who saved the lot.
  await owner.goto(lot8Url);
  await owner.getByLabel("Price (whole dollars)").fill("479000");
  await owner.getByRole("button", { name: "Save lot" }).click();
  await expect(owner.getByText("$489,000 → $479,000")).toBeVisible();
  await mailShot(mail, request, BUYER, "Lot 8 at Juniper Bench", "31-email-saved-lot");

  await owner.goto(`${lot8Url}/sign`);
  await expect(owner.getByRole("heading", { name: "Sign for Lot 8" })).toBeVisible();
  await shot(owner, "27-portal-sign");
  await owner.emulateMedia({ media: "print" });
  await owner.getByRole("article", { name: "Sign" }).screenshot({
    path: path.join(OUT, "28-printed-sign.png"),
  });
  await owner.emulateMedia({ media: "screen" });

  // --- the buyer's account ----------------------------------------------------------------
  await buyer.goto("/account");
  await expect(buyer.getByRole("heading", { name: "Your account" })).toBeVisible();
  await shot(buyer, "18-account", true);

  // --- offline -------------------------------------------------------------------------------
  const offlineContext = await newContext(browser);
  const offline = await offlineContext.newPage();
  await offline.goto("/juniper-bench/lots/8");
  await offline.waitForFunction(() => navigator.serviceWorker.controller !== null);
  await expect
    .poll(
      () =>
        offline.evaluate(async () =>
          Boolean(await (await caches.open("pages")).match("/juniper-bench")),
        ),
      { timeout: 20_000 },
    )
    .toBe(true);
  await offlineContext.setOffline(true);
  await offline.goto("/juniper-bench/lots/9");
  await expect(offline.getByRole("heading", { name: "You're offline" })).toBeVisible();
  await shot(offline, "19-offline");

  // Sizes, so the in-app guide can lay images out before they load.
  const sizes: Record<string, { width: number; height: number }> = {};
  for (const file of readdirSync(OUT).filter((name) => name.endsWith(".png")).sort()) {
    const { width, height } = PNG.sync.read(readFileSync(path.join(OUT, file)));
    sizes[file.replace(/\.png$/, "")] = { width, height };
  }
  writeFileSync(SIZES, `${JSON.stringify(sizes, null, 2)}\n`);
});
