# ADR-026: Lot geometry, the plat overlay and the first public map

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-06

## Context

P1-06 asks owners to draw and edit lot polygons, import GeoJSON and use an optional plat image
overlay, and for a drawn lot to render on the public map. The public pages and the GraphQL
endpoint that ADR-007 requires for public reads are otherwise P1-07's. The plan names no drawing
library and says nothing about validating shapes or how acreage relates to them.

## Decision

- **A minimal public map now.** Scott chose (2026-10-01) to pull forward the public GraphQL
  endpoint (`/graphql`, Strawberry, read-only, queries only, depth and token limits) with one
  query, `subdivision(slug)`, and a bare `/{slug}` page with the status-coloured map and lot
  list. Every resolver runs as `cornerpin_public`, so RLS alone decides visibility. P1-07 builds
  the rest of the public pages on it. GraphQL types for the web app are generated
  (graphql-codegen) with the `GeoJSON` scalar typed as a GeoJSON MultiPolygon.
- **Drawing with MapLibre and terra-draw.** terra-draw is maintained and supports MapLibre
  directly. The editor works one polygon at a time; a lot whose shape has several parts keeps
  only the first when edited, and says so.
- **Shapes in and out.** The API takes GeoJSON Polygon or MultiPolygon in longitude/latitude
  and stores MultiPolygon, SRID 4326. A shape must be valid to PostGIS (enforced by a CHECK) and
  within 25 km of the subdivision; coordinates outside longitude/latitude ranges are refused
  with a hint that the file is projected. Overlapping interiors are reported, not refused;
  shared edges are normal.
- **Acreage follows the shape.** A trigger sets acreage from the boundary's area whenever a
  boundary is saved. Clearing a shape keeps the last acreage, which becomes editable again.
- **GeoJSON import matches by lot number.** The number comes from the first of `number`, `lot`,
  `lot_number`, `lot_no`, `lotnum`, `lot_num`, `name`, `id` (any case), with a leading "Lot" or
  "#" removed. Import previews first and applies on request; unusable features are skipped with
  a reason while the rest apply; lots missing from the file are listed; missing lots can be
  created in a chosen phase.
- **The plat overlay is per subdivision and owner-only.** An image (re-encoded like photos, up to
  4096 px) placed over the lots, aligned by dragging four corner pins, with adjustable
  see-through. Stored through the storage interface (ADR-025); never public.
- **MapLibre's worker is served as a static file.** MapLibre 6 loads its worker as a separate
  module that the bundler does not emit; `scripts/copy-maplibre-worker.mjs` copies it from the
  installed package into `public/maplibre/` on every dev start and build.
- **Status colours are fixed.** Available green, on hold amber, sold grey. They encode meaning,
  so a future brand does not change them.

## Consequences

- The acceptance check (draw, round-trip, public map) runs in Playwright at both widths; the
  public map exposes the lot numbers it drew in a `data-rendered-lots` attribute for that.
- The subdivision's own outline (`subdivisions.boundary`) is not edited yet; the map frames the
  lots instead.
- Public pages are not cached yet; P1-07 decides caching with link previews and SSR.

## Related

ADR-004 (Next.js), ADR-005 (PWA), ADR-007 (GraphQL), ADR-018 (map tiles), ADR-025 (storage)
