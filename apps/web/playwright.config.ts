import { defineConfig, devices } from "@playwright/test";

const webPort = 3100;
const apiPort = 8100;
const baseURL = `http://localhost:${webPort}`;

const mobile = { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 } };
const desktop = { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } };

// Smoke tests run against a production build so the service worker and manifest behave as
// they will when deployed. The API runs on its own throwaway database (cornerpin_e2e) and sends
// email to Mailpit, so `docker compose up -d` must be running.
//
// Portal and buyer tests reuse sessions saved by portal.setup.ts, one per viewport.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /portal\.setup\.ts/ },
    { name: "mobile", use: mobile, testIgnore: /(portal|buyer)\./ },
    { name: "desktop", use: desktop, testIgnore: /(portal|buyer)\./ },
    {
      name: "mobile-portal",
      use: { ...mobile, storageState: "playwright/.auth/portal-mobile.json" },
      testMatch: /portal\.spec\.ts/,
      dependencies: ["setup"],
    },
    {
      name: "desktop-portal",
      use: { ...desktop, storageState: "playwright/.auth/portal-desktop.json" },
      testMatch: /portal\.spec\.ts/,
      dependencies: ["setup"],
    },
    {
      name: "mobile-buyer",
      use: { ...mobile, storageState: "playwright/.auth/buyer-mobile.json" },
      testMatch: /buyer\.spec\.ts/,
      dependencies: ["setup"],
    },
    {
      name: "desktop-buyer",
      use: { ...desktop, storageState: "playwright/.auth/buyer-desktop.json" },
      testMatch: /buyer\.spec\.ts/,
      dependencies: ["setup"],
    },
  ],
  webServer: [
    {
      command: `uv run python -m cornerpin.e2e_server ${apiPort}`,
      cwd: "../..",
      url: `http://localhost:${apiPort}/v1/health`,
      env: { WEB_ORIGIN: baseURL },
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `pnpm build && pnpm exec next start --port ${webPort}`,
      url: baseURL,
      env: { API_BASE_URL: `http://localhost:${apiPort}`, SITE_URL: baseURL },
      reuseExistingServer: !process.env.CI,
      timeout: 240_000,
    },
  ],
});
