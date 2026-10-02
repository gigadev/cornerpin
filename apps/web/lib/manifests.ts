import type { MetadataRoute } from "next";

// Web app manifests (ADR-005, ADR-030): one for the site, one per subdivision so a buyer can
// install the subdivision they're standing in, and one for the owner portal. A scope has no
// trailing slash because the pages are served without one ("/juniper-bench", not
// "/juniper-bench/"), and a start URL must be inside its scope.

type Manifest = MetadataRoute.Manifest;

const SHARED = {
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
} satisfies Manifest;

export function siteManifest(): Manifest {
  return {
    ...SHARED,
    id: "/",
    name: "Cornerpin",
    short_name: "Cornerpin",
    description: "Subdivision lots: status, price, maps, photos and documents.",
    start_url: "/",
    scope: "/",
  };
}

export function subdivisionManifest({ slug, name }: { slug: string; name: string }): Manifest {
  return {
    ...SHARED,
    id: `/${slug}/`,
    name: `${name} · Cornerpin`,
    short_name: name,
    description: `Lots at ${name}: status, price, map, photos and documents.`,
    start_url: `/${slug}`,
    scope: `/${slug}`,
  };
}

export function portalManifest(): Manifest {
  return {
    ...SHARED,
    id: "/app/",
    name: "Cornerpin owner portal",
    short_name: "Cornerpin owner",
    description: "Manage subdivisions, lots, inquiries and holds.",
    start_url: "/app",
    scope: "/app",
  };
}

export function manifestResponse(manifest: Manifest): Response {
  return new Response(JSON.stringify(manifest), {
    headers: {
      "content-type": "application/manifest+json",
      "cache-control": "public, max-age=3600",
    },
  });
}
