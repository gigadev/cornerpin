import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";
import { API_URL, DEMO_LOTS, DEMO_TENANT_ID, clearInbox, signInLink } from "./fixtures";

// P2-03: the unsubscribe link in an outreach email works signed out, and only the button
// changes anything. The link is signed here the way the API signs it, with the local
// development secret; the API's tests cover links from real sends.

const LOCAL_SECRET = "local-development-only-not-a-secret";

function b64(data: string | Buffer): string {
  return Buffer.from(data).toString("base64url");
}

function unsubscribeToken(tenantId: string, userId: string): string {
  const body = b64(
    JSON.stringify({ v: { t: tenantId, u: userId, c: "email" }, t: Math.floor(Date.now() / 1000) }),
  );
  return `${body}.${b64(createHmac("sha256", LOCAL_SECRET).update(body).digest())}`;
}

test("a buyer stops an owner's emails from the link, without signing in", async ({
  browser,
}, testInfo) => {
  // A buyer of their own, so no other test sees their permissions change.
  const email = `unsub+${testInfo.project.name}-${Date.now()}@buyers.cornerpin.test`;
  const fresh = { storageState: { cookies: [], origins: [] } };
  const buyer = await (await browser.newContext(fresh)).newPage();
  await clearInbox(buyer.request, email);
  const requested = await buyer.request.post("/v1/auth/magic-link", {
    data: { email, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/" },
  });
  expect(requested.status()).toBe(202);
  const signIn = new URL(await signInLink(buyer.request, email)).searchParams.get("token");
  const verified = await buyer.request.post("/v1/auth/magic-link/verify", {
    data: { token: signIn },
  });
  expect(verified.ok()).toBe(true);

  // They ask about a lot and let the owner email them.
  const lookup = await buyer.request.post(`${API_URL}/graphql`, {
    data: {
      query: `{ lot(subdivisionSlug: "juniper-bench", number: "${DEMO_LOTS.home}") { id } }`,
    },
  });
  const { data } = (await lookup.json()) as { data: { lot: { id: string } } };
  const asked = await buyer.request.post(`/v1/lots/${data.lot.id}/inquiries`, {
    data: { name: "Unsub Tester", message: "Is it flat?", contact: { email: true } },
  });
  expect(asked.status()).toBe(201);
  const me = (await (await buyer.request.get("/v1/me")).json()) as { id: string };

  const visitor = await (await browser.newContext(fresh)).newPage();
  await visitor.goto(`/unsubscribe?token=${unsubscribeToken(DEMO_TENANT_ID, me.id)}`);
  await expect(visitor.getByRole("heading", { name: "Unsubscribe" })).toBeVisible();
  await expect(visitor.getByText("Stop Demo Land Co. sending you email")).toBeVisible();
  await visitor.getByRole("button", { name: "Stop email from Demo Land Co." }).click();
  await expect(visitor.getByRole("status")).toContainText("Demo Land Co. won't send you email");

  await buyer.goto("/account");
  const permissions = buyer.getByRole("region", { name: "Who may contact you" });
  await expect(permissions.getByLabel("Email from Demo Land Co.")).not.toBeChecked();

  // A link that was cut short says so.
  await visitor.goto("/unsubscribe?token=broken");
  await expect(visitor.getByText("This link doesn't work")).toBeVisible();
});
