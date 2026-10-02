import { withSerwist } from "@serwist/turbopack";
import path from "node:path";
import type { NextConfig } from "next";

// The web image builds a standalone server (apps/web/Dockerfile sets NEXT_OUTPUT); local runs
// and Playwright use `next start` as before.
const standalone = process.env.NEXT_OUTPUT === "standalone";

const nextConfig: NextConfig = {
  ...(standalone
    ? { output: "standalone", outputFileTracingRoot: path.resolve(process.cwd(), "../..") }
    : {}),
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    // The image optimiser may fetch public photos only. Owner-portal photos need the session
    // cookie, which the optimiser does not send, so they are shown unoptimised (ADR-027).
    // The guide's screenshots (/help) are resized the same way.
    localPatterns: [{ pathname: "/v1/public/photos/**" }, { pathname: "/walkthrough/**" }],
  },
};

export default withSerwist(nextConfig);
