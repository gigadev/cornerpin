import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PublicLotMap } from "@/components/map/public-lot-map";
import { StatusBadge } from "@/components/portal/status-badge";
import { SiteHeader } from "@/components/site-header";
import { publicQuery } from "@/lib/graphql/client";
import { PublicSubdivisionMapDocument } from "@/lib/graphql/generated";
import { formatAcres, formatPrice } from "@/lib/format";
import { lotStatusFromGraphql, type MapLotInput } from "@/lib/map/lots";

// The public subdivision page, minimal for now: the map coloured by status and the lot list.
// P1-07 adds lot pages, filters, photos, documents and link previews (ADR-006, ADR-007).

async function load(slug: string) {
  const { subdivision } = await publicQuery(PublicSubdivisionMapDocument, { slug });
  return subdivision;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const subdivision = await load((await params).slug);
  return subdivision ? { title: `${subdivision.name} · Cornerpin` } : {};
}

export default async function SubdivisionPage({ params }: { params: Promise<{ slug: string }> }) {
  const subdivision = await load((await params).slug);
  if (!subdivision) notFound();

  const lots: MapLotInput[] = subdivision.lots.map((lot) => ({
    id: lot.id,
    number: lot.number,
    status: lotStatusFromGraphql(lot.status),
    boundary: lot.boundary,
  }));
  const [lng = 0, lat = 0] = subdivision.center;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{subdivision.name}</h1>
          {subdivision.description ? (
            <p className="mt-2 max-w-prose text-muted-foreground">{subdivision.description}</p>
          ) : null}
        </div>
        <PublicLotMap
          center={[lng, lat]}
          lots={lots}
          satelliteKey={process.env.MAPTILER_KEY ?? null}
        />
        <section aria-labelledby="lots-heading">
          <h2 id="lots-heading" className="mb-2 text-lg font-semibold">
            Lots
          </h2>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {subdivision.lots.map((lot) => (
              <li key={lot.id} className="flex flex-wrap items-center gap-3 px-4 py-2">
                <span className="font-medium">Lot {lot.number}</span>
                <StatusBadge status={lotStatusFromGraphql(lot.status)} />
                <span className="ml-auto tabular-nums">{formatPrice(lot.price)}</span>
                <span className="w-20 text-right text-sm text-muted-foreground tabular-nums">
                  {formatAcres(lot.acreage)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}
