import { formatPrice } from "@/lib/format";
import { publicQuery } from "@/lib/graphql/client";
import { PublicSubdivisionMapDocument } from "@/lib/graphql/generated";
import { OG_SIZE, ogCard } from "@/lib/og-card";

export const size = OG_SIZE;
export const contentType = "image/png";
export const alt = "A subdivision on Cornerpin";

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { subdivision } = await publicQuery(PublicSubdivisionMapDocument, {
    slug: (await params).slug,
  });
  if (!subdivision) return ogCard({ eyebrow: "Cornerpin", title: "Subdivision lots", lines: [] });

  const available = subdivision.lots.filter((lot) => lot.status === "AVAILABLE");
  const prices = available.map((lot) => lot.price).filter((price) => price !== null);
  const lines = [`${available.length} of ${subdivision.lots.length} lots available`];
  if (prices.length > 0) lines.push(`From ${formatPrice(Math.min(...prices))}`);
  return ogCard({ eyebrow: "Lots for sale", title: subdivision.name, lines });
}
