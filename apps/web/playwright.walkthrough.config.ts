import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.config";

// Screenshots for the in-app guide (/help) and docs/WALKTHROUGH.md: `pnpm walkthrough`. Same
// throwaway stack as the Playwright tests (production build, fresh cornerpin_e2e database,
// Mailpit), one browser. The web app believes it's cornerpin.app, so signs and links in the
// screenshots show the real address.
const servers = Array.isArray(base.webServer) ? base.webServer : [];

export default defineConfig({
  ...base,
  webServer: servers.map((server) =>
    server.env?.SITE_URL
      ? { ...server, env: { ...server.env, SITE_URL: "https://cornerpin.app" } }
      : server,
  ),
  testDir: "./walkthrough",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  projects: [
    {
      name: "walkthrough",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
});
