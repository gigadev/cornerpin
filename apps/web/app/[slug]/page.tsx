import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PublicLotMap } from "@/components/map/public-lot-map";
import { StatusBadge } from "@/components/portal/status-badge";
import { LotFilterForm } from "@/components/public/lot-filter-form";
import { SiteHeader } from "@/components/site-header";
import { formatAcres, formatPrice, listingLabel } from "@/lib/format";
import { publicQuery } from "@/lib/graphql/client";
import { listingTypeFromGraphql } from "@/lib/graphql/enums";
import { PublicSubdivisionMapDocument } from "@/lib/graphql/generated";
import { applyFilters, hasFilters, parseFilters } from "@/lib/lot-filters";
import { lotStatusFromGraphql, type MapLotInput } from "@/lib/map/lots";

// The public subdivision page (P1-07): map coloured by status, filters and the lot list.
// Rendered on the server, so everything but the map works without JavaScript.

type Params = Promise<{ slug: string }>;
type SearchParams = Promise<Record<string, string | string[] | undefined>>;

async function load(slug: string) {
  const { subdivision } = await publicQuery(PublicSubdivisionMapDocument, { slug });
  return subdivision;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const subdivision = await load((await params).slug);
  if (!subdivision) return {};
  const available = subdivision.lots.filter((lot) => lot.status === "AVAILABLE").length;
  const summary = `${available} of ${subdivision.lots.length} lots available.`;
  const description = subdivision.description ? `${summary} ${subdivision.description}` : summary;
  return {
    title: `${subdivision.name} · Cornerpin`,
    description,
    alternates: { canonical: `/${subdivision.slug}` },
    manifest: `/${subdivision.slug}/manifest.webmanifest`,
    openGraph: {
      type: "website",
      title: subdivision.name,
      description,
      url: `/${subdivision.slug}`,
      siteName: "Cornerpin",
    },
    twitter: { card: "summary_large_image", title: subdivision.name, description },
  };
}

export default async function SubdivisionPage({
  params,
  searchParams,
}: {
  params: Params;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const subdivision = await load(slug);
  if (!subdivision) notFound();

  const filters = parseFilters(await searchParams);
  const lots = subdivision.lots.map((lot) => ({
    ...lot,
    status: lotStatusFromGraphql(lot.status),
    listingType: listingTypeFromGraphql(lot.listingType),
  }));
  const shown = applyFilters(lots, filters);
  const phases = [...new Set(lots.map((lot) => lot.phaseName))];
  const mapLots: MapLotInput[] = shown.map(({ id, number, status, boundary }) => ({
    id,
    number,
    status,
    boundary,
  }));
  const [lng = 0, lat = 0] = subdivision.center;
  const lotPath = `/${subdivision.slug}/lots/`;

  return (
    <>
      <SiteHeader>
        <Link href="/account" className="underline">
          Account
        </Link>
      </SiteHeader>
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{subdivision.name}</h1>
          {subdivision.description ? (
            <p className="mt-2 max-w-prose text-muted-foreground">{subdivision.description}</p>
          ) : null}
        </div>

        <PublicLotMap
          center={[lng, lat]}
          lots={mapLots}
          linkBase={lotPath}
          satelliteKey={process.env.MAPTILER_KEY ?? null}
        />

        <section aria-labelledby="lots-heading" className="grid gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="lots-heading" className="text-lg font-semibold">
              Lots
            </h2>
            <p role="status" className="text-sm text-muted-foreground">
              {hasFilters(filters)
                ? `Showing ${shown.length} of ${lots.length} lots`
                : `${lots.length} lots`}
            </p>
          </div>
          <LotFilterForm action={`/${subdivision.slug}`} filters={filters} phases={phases} />
          {shown.length === 0 ? (
            <p className="text-muted-foreground">No lots match. Try fewer filters.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {shown.map((lot) => (
                <li key={lot.id}>
                  <Link
                    href={`${lotPath}${encodeURIComponent(lot.number)}`}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-muted"
                  >
                    <span className="font-medium">Lot {lot.number}</span>
                    <StatusBadge status={lot.status} />
                    <span className="text-sm text-muted-foreground">
                      {listingLabel(lot.listingType)}
                      {phases.length > 1 ? ` · ${lot.phaseName}` : ""}
                    </span>
                    <span className="ml-auto tabular-nums">{formatPrice(lot.price)}</span>
                    <span className="w-20 text-right text-sm text-muted-foreground tabular-nums">
                      {formatAcres(lot.acreage)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  );
}
