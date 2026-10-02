import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { PublicLotMap } from "@/components/map/public-lot-map";
import { StatusBadge } from "@/components/portal/status-badge";
import { SiteHeader } from "@/components/site-header";
import { buttonVariants } from "@/components/ui/button";
import { directionsUrl } from "@/lib/directions";
import {
  documentLabel,
  formatAcres,
  formatBytes,
  formatPrice,
  listingLabel,
  statusLabel,
} from "@/lib/format";
import { publicQuery } from "@/lib/graphql/client";
import { documentKindFromGraphql, listingTypeFromGraphql } from "@/lib/graphql/enums";
import { PublicLotPageDocument } from "@/lib/graphql/generated";
import { lotStatusFromGraphql, type MapLotInput } from "@/lib/map/lots";

// The public lot page (P1-07): price, status, photos, documents, a map and directions.
// Rendered on the server; it all works without JavaScript except the map.

type Params = Promise<{ slug: string; number: string }>;

const load = cache(async (slug: string, number: string) =>
  publicQuery(PublicLotPageDocument, { slug, number: decodeURIComponent(number) }),
);

function homeSummary(home: { bedrooms: number | null; bathrooms: number | null; squareFeet: number | null }) {
  return [
    home.bedrooms !== null ? `${home.bedrooms} bed` : null,
    home.bathrooms !== null ? `${home.bathrooms} bath` : null,
    home.squareFeet !== null ? `${home.squareFeet.toLocaleString("en-US")} sq ft` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug, number } = await params;
  const { subdivision, lot } = await load(slug, number);
  if (!subdivision || !lot) return {};
  const title = `Lot ${lot.number}, ${subdivision.name}`;
  const facts = [
    statusLabel(lotStatusFromGraphql(lot.status)),
    formatPrice(lot.price),
    lot.acreage !== null ? formatAcres(lot.acreage) : null,
    lot.home ? homeSummary(lot.home) || "Lot + home" : null,
  ].filter(Boolean);
  const description = facts.join(" · ");
  const url = `/${subdivision.slug}/lots/${encodeURIComponent(lot.number)}`;
  return {
    title: `${title} · Cornerpin`,
    description,
    alternates: { canonical: url },
    openGraph: { type: "website", title, description, url, siteName: "Cornerpin" },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function LotPage({ params }: { params: Params }) {
  const { slug, number } = await params;
  const { subdivision, lot } = await load(slug, number);
  if (!subdivision || !lot) notFound();

  const status = lotStatusFromGraphql(lot.status);
  const listing = listingTypeFromGraphql(lot.listingType);
  const [lng = 0, lat = 0] = lot.location;
  const [centerLng = 0, centerLat = 0] = subdivision.center;
  const mapLots: MapLotInput[] = subdivision.lots.map((other) => ({
    id: other.id,
    number: other.number,
    status: lotStatusFromGraphql(other.status),
    boundary: other.boundary,
  }));
  const [cover, ...gallery] = lot.photos;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto grid max-w-5xl gap-6 px-4 py-8">
        <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
          <Link href={`/${subdivision.slug}`} className="underline-offset-4 hover:underline">
            {subdivision.name}
          </Link>
        </nav>

        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Lot {lot.number}</h1>
            <StatusBadge status={status} />
          </div>
          <p className="text-2xl tabular-nums">{formatPrice(lot.price)}</p>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border border-border p-4 sm:grid-cols-4">
          <div>
            <dt className="text-sm text-muted-foreground">Size</dt>
            <dd>{formatAcres(lot.acreage)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Listing</dt>
            <dd>{listingLabel(listing)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Phase</dt>
            <dd>{lot.phaseName}</dd>
          </div>
          {lot.home ? (
            <div>
              <dt className="text-sm text-muted-foreground">Home</dt>
              <dd>{homeSummary(lot.home) || "Details to come"}</dd>
            </div>
          ) : null}
        </dl>
        {lot.home?.description ? <p className="max-w-prose">{lot.home.description}</p> : null}

        {cover ? (
          <section aria-labelledby="photos-heading" className="grid gap-3">
            <h2 id="photos-heading" className="text-lg font-semibold">
              Photos
            </h2>
            <figure className="grid gap-1">
              <Image
                src={cover.url}
                alt={cover.caption || `Lot ${lot.number}`}
                width={cover.width ?? 1600}
                height={cover.height ?? 1200}
                sizes="(min-width: 1024px) 1000px, 100vw"
                priority
                className="max-h-[70vh] w-full rounded-lg bg-muted object-cover"
              />
              {cover.caption ? (
                <figcaption className="text-sm text-muted-foreground">{cover.caption}</figcaption>
              ) : null}
            </figure>
            {gallery.length > 0 ? (
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {gallery.map((photo) => (
                  <li key={photo.id}>
                    <figure className="grid gap-1">
                      <Image
                        src={photo.url}
                        alt={photo.caption || `Lot ${lot.number}`}
                        width={photo.width ?? 800}
                        height={photo.height ?? 600}
                        sizes="(min-width: 640px) 33vw, 50vw"
                        className="aspect-[4/3] w-full rounded-md bg-muted object-cover"
                      />
                      {photo.caption ? (
                        <figcaption className="text-sm text-muted-foreground">
                          {photo.caption}
                        </figcaption>
                      ) : null}
                    </figure>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}

        <section aria-labelledby="where-heading" className="grid gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="where-heading" className="text-lg font-semibold">
              Where it is
            </h2>
            <a
              href={directionsUrl(lng, lat)}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonVariants({ size: "lg" })}
            >
              Directions
            </a>
          </div>
          <PublicLotMap
            center={[centerLng, centerLat]}
            lots={mapLots}
            focusLotId={lot.id}
            linkBase={`/${subdivision.slug}/lots/`}
            size="short"
            satelliteKey={process.env.MAPTILER_KEY ?? null}
          />
        </section>

        {lot.documents.length > 0 ? (
          <section aria-labelledby="documents-heading" className="grid gap-2">
            <h2 id="documents-heading" className="text-lg font-semibold">
              Documents
            </h2>
            <ul className="divide-y divide-border rounded-lg border border-border">
              {lot.documents.map((document) => (
                <li key={document.id} className="flex flex-wrap items-center gap-3 px-4 py-2">
                  <span className="w-24 text-sm text-muted-foreground">
                    {documentLabel(documentKindFromGraphql(document.kind))}
                  </span>
                  <a href={document.url} download className="font-medium underline">
                    {document.title}
                  </a>
                  <span className="ml-auto text-sm text-muted-foreground">
                    {formatBytes(document.sizeBytes)}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <p>
          <Link href={`/${subdivision.slug}`} className="underline">
            All lots in {subdivision.name}
          </Link>
        </p>
      </main>
    </>
  );
}
