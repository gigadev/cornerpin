import { randomUUID } from "node:crypto";
import { createSerwistRoute } from "@serwist/turbopack";

// Builds app/sw.ts with esbuild and serves it at /serwist/sw.js with
// Service-Worker-Allowed: / so it can control the whole origin (ADR-005). The build's static
// files and the offline page are precached; the offline page's revision changes every build.
export const { dynamic, dynamicParams, revalidate, generateStaticParams, GET } = createSerwistRoute({
  swSrc: "app/sw.ts",
  useNativeEsbuild: true,
  additionalPrecacheEntries: [{ url: "/offline", revision: randomUUID() }],
  // The help page's screenshots load only on /help; every visitor shouldn't download them.
  globIgnores: ["**/node_modules/**/*", "public/walkthrough/**/*"],
});
