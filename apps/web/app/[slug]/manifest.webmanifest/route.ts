import { publicQuery } from "@/lib/graphql/client";
import { SubdivisionManifestDocument } from "@/lib/graphql/generated";
import { manifestResponse, subdivisionManifest } from "@/lib/manifests";

// Each published subdivision installs as its own app, scoped to its pages (ADR-030).
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ slug: string }> },
): Promise<Response> {
  const { slug } = await params;
  const { subdivision } = await publicQuery(SubdivisionManifestDocument, { slug });
  if (!subdivision) return new Response("Not found", { status: 404 });
  return manifestResponse(subdivisionManifest(subdivision));
}
