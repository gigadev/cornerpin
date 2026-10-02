import { withSerwist } from "@serwist/turbopack";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    // The image optimiser may fetch public photos only. Owner-portal photos need the session
    // cookie, which the optimiser does not send, so they are shown unoptimised (ADR-027).
    localPatterns: [{ pathname: "/v1/public/photos/**" }],
  },
};

export default withSerwist(nextConfig);
