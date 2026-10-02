import { manifestResponse, portalManifest } from "@/lib/manifests";

// The owner portal installs on its own (ADR-005); it stays online-only.
export const dynamic = "force-static";

export function GET(): Response {
  return manifestResponse(portalManifest());
}
