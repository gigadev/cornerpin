import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { PublicLotMap } from "@/components/map/public-lot-map";
import { BuyerLotProvider, SaveLotButton } from "@/components/public/buyer-lot";
import { ContactOwner } from "@/components/public/contact-owner";
import { StatusBadge } from "@/components/portal/status-badge";
import { SiteHeader } from "@/components/site-header";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
// Rendered on the server; it all works without JavaScript except the map and the buyer's own
// activity (P1-08), which the browser asks the API for so the page stays the same for everyone.

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
    manifest: `/${subdivision.slug}/manifest.webmanifest`,
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
  const lotPath = `/${subdivision.slug}/lots/${encodeURIComponent(lot.number)}`;

  return (
    <BuyerLotProvider lotId={lot.id} lotPath={lotPath}>
      <SiteHeader>
        <Link href="/account">Account</Link>
      </SiteHeader>
      <main>
        <section className="contours border-b border-border">
          <div className="mx-auto grid max-w-5xl gap-3 px-4 py-8 sm:py-12">
            <nav aria-label="Breadcrumb" className="text-sm font-medium text-primary">
              <Link href={`/${subdivision.slug}`} className="underline-offset-4 hover:underline">
                {subdivision.name}
              </Link>
            </nav>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Lot {lot.number}</h1>
              <StatusBadge status={status} />
            </div>
            <p className="font-heading text-3xl font-medium tabular-nums">
              {formatPrice(lot.price)}
            </p>
            <div className="flex flex-wrap gap-3 pt-1">
              <a href="#contact" className={cn(buttonVariants({ size: "lg" }), "h-10 px-4")}>
                Contact the owner
              </a>
              <SaveLotButton />
            </div>
          </div>
        </section>

        <div className="mx-auto grid max-w-5xl gap-8 px-4 py-8">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl border border-border bg-card p-5 sm:grid-cols-4">
            <div>
              <dt className="text-sm text-muted-foreground">Size</dt>
              <dd className="font-medium">{formatAcres(lot.acreage)}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Listing</dt>
              <dd className="font-medium">{listingLabel(listing)}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">Phase</dt>
              <dd className="font-medium">{lot.phaseName}</dd>
            </div>
            {lot.home ? (
              <div>
                <dt className="text-sm text-muted-foreground">Home</dt>
                <dd className="font-medium">{homeSummary(lot.home) || "Details to come"}</dd>
              </div>
            ) : null}
          </dl>
          {lot.home?.description ? <p className="max-w-prose">{lot.home.description}</p> : null}

          {cover ? (
            <section aria-labelledby="photos-heading" className="grid gap-3">
              <h2 id="photos-heading" className="text-2xl font-semibold tracking-tight">
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
                  className="max-h-[70vh] w-full rounded-xl bg-muted object-cover shadow-sm"
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
              <h2 id="where-heading" className="text-2xl font-semibold tracking-tight">
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
              <h2 id="documents-heading" className="text-2xl font-semibold tracking-tight">
                Documents
              </h2>
              <ul className="divide-y divide-border rounded-xl border border-border bg-card">
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

          <section
            id="contact"
            aria-labelledby="contact-heading"
            className="grid scroll-mt-4 gap-3"
          >
            <h2 id="contact-heading" className="text-2xl font-semibold tracking-tight">
              Contact the owner
            </h2>
            <noscript>
              <p className="text-sm text-muted-foreground">The contact form needs JavaScript.</p>
            </noscript>
            <ContactOwner
              lotLabel={`Lot ${lot.number}, ${subdivision.name}`}
              subdivisionName={subdivision.name}
              available={status === "available"}
            />
          </section>

          <p>
            <Link href={`/${subdivision.slug}`} className="underline">
              All lots in {subdivision.name}
            </Link>
          </p>
        </div>
      </main>
    </BuyerLotProvider>
  );
}
