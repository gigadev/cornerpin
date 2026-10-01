import { expect, test } from "@playwright/test";
import {
  DEMO_TENANT_ID,
  OTHER_TENANT_ID,
  clearInbox,
  projectOwner,
  signInLink,
} from "./fixtures";

// P1-03 acceptance: sign in through Mailpit; an owner cannot reach another tenant's portal.

test("signed-out visitors are sent to sign in", async ({ page }) => {
  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await expect(page).toHaveURL(/\/signin\?next=\/app$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
});

test("owner signs in by email link and reaches only their own portal", async ({
  page,
  request,
}, testInfo) => {
  const owner = projectOwner(testInfo);
  await clearInbox(request, owner);

  await page.goto("/app");
  await page.getByLabel("Email").fill(owner);
  // Cloudflare's test site key passes without interaction once the widget has loaded.
  const send = page.getByRole("button", { name: "Email me a sign-in link" });
  await expect(send).toBeEnabled({ timeout: 15_000 });
  await send.click();
  await expect(page.getByRole("status")).toContainText("Check your email");

  const link = await signInLink(request, owner);
  await page.goto(link);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("link", { name: /Demo Land Co\./ }).click();
  await expect(page).toHaveURL(new RegExp(`/app/${DEMO_TENANT_ID}$`));
  await expect(page.getByRole("heading", { name: "Demo Land Co." })).toBeVisible();

  // Another tenant's portal: not found, through the page and through the API.
  const otherPage = await page.goto(`/app/${OTHER_TENANT_ID}`);
  expect(otherPage?.status()).toBe(404);
  await expect(page.getByText("Other Land Co.")).toHaveCount(0);
  const otherApi = await page.request.get(`/v1/tenants/${OTHER_TENANT_ID}`);
  expect(otherApi.status()).toBe(404);

  // Signing out ends the session.
  await page.goto("/app");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/signin/);
});

test("a used sign-in link cannot be used again", async ({ page, request }, testInfo) => {
  // A new address: this also covers sign-up, and keeps this test out of the owner's inbox.
  const visitor = `visitor+${testInfo.project.name}-${Date.now()}@cornerpin.test`;
  const response = await page.request.post("/v1/auth/magic-link", {
    data: { email: visitor, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/app" },
  });
  expect(response.status()).toBe(202);
  const link = await signInLink(request, visitor);

  await page.goto(link);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);

  await page.context().clearCookies();
  await page.goto(link);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("This sign-in link has expired or was already used")).toBeVisible();
});
