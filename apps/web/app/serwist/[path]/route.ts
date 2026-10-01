import { createSerwistRoute } from "@serwist/turbopack";

// Builds app/sw.ts with esbuild and serves it at /serwist/sw.js with
// Service-Worker-Allowed: / so it can control the whole origin (ADR-005).
export const { dynamic, dynamicParams, revalidate, generateStaticParams, GET } = createSerwistRoute({
  swSrc: "app/sw.ts",
  useNativeEsbuild: true,
});
