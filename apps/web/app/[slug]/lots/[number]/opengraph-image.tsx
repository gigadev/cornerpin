import { formatAcres, formatPrice, statusLabel } from "@/lib/format";
import { publicQuery } from "@/lib/graphql/client";
import { PublicLotPageDocument } from "@/lib/graphql/generated";
import { lotStatusFromGraphql } from "@/lib/map/lots";
import { OG_SIZE, ogCard } from "@/lib/og-card";

export const size = OG_SIZE;
export const contentType = "image/png";
export const alt = "A lot on Cornerpin";

export default async function Image({
  params,
}: {
  params: Promise<{ slug: string; number: string }>;
}) {
  const { slug, number } = await params;
  const { subdivision, lot } = await publicQuery(PublicLotPageDocument, {
    slug,
    number: decodeURIComponent(number),
  });
  if (!subdivision || !lot) return ogCard({ eyebrow: "Cornerpin", title: "Lot", lines: [] });

  const facts = [statusLabel(lotStatusFromGraphql(lot.status)), formatPrice(lot.price)];
  if (lot.acreage !== null) facts.push(formatAcres(lot.acreage));
  return ogCard({
    eyebrow: subdivision.name,
    title: `Lot ${lot.number}`,
    lines: [facts.join(" · "), ...(lot.home ? ["Lot + home"] : [])],
  });
}
