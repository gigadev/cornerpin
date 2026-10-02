import { manifestResponse, siteManifest } from "@/lib/manifests";

export const dynamic = "force-static";

export function GET(): Response {
  return manifestResponse(siteManifest());
}
