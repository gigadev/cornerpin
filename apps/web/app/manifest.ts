import type { MetadataRoute } from "next";

// App-wide manifest for the shell. Per-subdivision manifests (scope /{slug}/) and the owner
// portal manifest (scope /app/) arrive with the pages they belong to (ADR-005).
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/",
    name: "Cornerpin",
    short_name: "Cornerpin",
    description: "Subdivision lots: status, price, maps, photos and documents.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: "#fafaf9",
    theme_color: "#1c1917",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
