import { expect, test as setup } from "@playwright/test";
import { clearInbox, signInLink } from "./fixtures";

// Signs in one portal owner per viewport and saves the session for portal.spec.ts. The UI
// sign-in flow itself is covered by auth.spec.ts; this goes through the API to stay quick.
for (const viewport of ["mobile", "desktop"] as const) {
  setup(`sign in the ${viewport} portal owner`, async ({ page, request }) => {
    const owner = `portal+${viewport}@demo.cornerpin.test`;
    await clearInbox(request, owner);
    const requested = await page.request.post("/v1/auth/magic-link", {
      data: { email: owner, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/app" },
    });
    expect(requested.status()).toBe(202);

    const token = new URL(await signInLink(request, owner)).searchParams.get("token");
    const verified = await page.request.post("/v1/auth/magic-link/verify", { data: { token } });
    expect(verified.ok()).toBe(true);

    await page.context().storageState({ path: `playwright/.auth/portal-${viewport}.json` });
  });
}
