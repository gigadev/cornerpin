# ADR-027: Public pages: rendering, filters, files and link previews

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-07

## Context

P1-07 builds the public subdivision and lot pages on ADR-026's GraphQL endpoint. They must render
without JavaScript, never show unpublished lots, and give good link previews; buyers often arrive
from a QR code on a sign with a weak signal (ADR-005). The plan doesn't say how filters work
without JavaScript, how public photos and documents are served, or what a directions link is.

## Decision

- **Server-rendered, fresh on each request.** Both pages render on the server from GraphQL with
  no caching, so publishing and status changes show at once. Caching is revisited with the PWA
  (P1-10) and the deployment (P1-12).
- **Filters are a GET form.** Status, listing type, phase, maximum price and minimum acres are
  query parameters, applied on the server; native form controls, so they work without
  JavaScript and a filtered list can be shared. A lot with no price or acreage doesn't pass a
  filter on that value.
- **Public files are REST, not GraphQL.** `/v1/public/photos/{id}/file` and
  `/v1/public/documents/{id}/file` serve bytes as `cornerpin_public`, so a file is reachable only
  while its lot and subdivision are published. Photos may be cached publicly for a day.
- **Public photos are optimised.** Next's image optimiser resizes them for each screen;
  `images.localPatterns` limits it to `/v1/public/photos/**`. Owner-portal photos stay
  unoptimised because the optimiser doesn't send the session cookie.
- **Directions are a Google Maps link** to a point inside the lot's shape (PostGIS
  `ST_PointOnSurface`), or the subdivision's location when the lot has no shape. It opens the app
  on phones and needs no key.
- **Link previews.** Each page sets Open Graph and Twitter tags and a canonical URL, and has a
  generated preview card (`opengraph-image.tsx`): plain neutral text with name, availability,
  price and acreage. `SITE_URL` makes the URLs absolute.
- **The map is an extra.** Without JavaScript a `<noscript>` note stands in for it; every lot is
  listed on the page anyway. With JavaScript, clicking a lot on the map opens its page, and a lot
  page frames and outlines its own lot.

## Consequences

- Each page view costs a GraphQL round trip; at this traffic that's fine.
- Playwright tests the no-JavaScript pages with scripts disabled. It can't show `<noscript>`
  content (its parser still treats scripting as on), so that test checks the HTML instead.
- A lot page's URL is its subdivision's slug plus the lot number, as ADR-006 set; renaming a slug
  changes it, which the QR redirects in P1-11 absorb.

## Related

ADR-005 (PWA), ADR-006 (URLs), ADR-007 (GraphQL), ADR-025 (storage), ADR-026 (public map)
