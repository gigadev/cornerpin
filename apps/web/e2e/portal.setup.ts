import { expect, test as setup } from "@playwright/test";
import { clearInbox, signInLink } from "./fixtures";

// Signs in one portal owner and one buyer per viewport and saves their sessions for
// portal.spec.ts and buyer.spec.ts. The UI sign-in flow itself is covered by auth.spec.ts;
// this goes through the API to stay quick. Buyers get an account on first sign-in.
const ACCOUNTS = [
  ["portal", "portal+{viewport}@demo.cornerpin.test"],
  ["buyer", "buyer+{viewport}@buyers.cornerpin.test"],
] as const;

for (const viewport of ["mobile", "desktop"] as const) {
  for (const [role, template] of ACCOUNTS) {
    setup(`sign in the ${viewport} ${role}`, async ({ page, request }) => {
      const email = template.replace("{viewport}", viewport);
      await clearInbox(request, email);
      const requested = await page.request.post("/v1/auth/magic-link", {
        data: { email, turnstile_token: "XXXX.DUMMY.TOKEN.XXXX", next: "/" },
      });
      expect(requested.status()).toBe(202);

      const token = new URL(await signInLink(request, email)).searchParams.get("token");
      const verified = await page.request.post("/v1/auth/magic-link/verify", { data: { token } });
      expect(verified.ok()).toBe(true);

      await page.context().storageState({ path: `playwright/.auth/${role}-${viewport}.json` });
    });
  }
}
