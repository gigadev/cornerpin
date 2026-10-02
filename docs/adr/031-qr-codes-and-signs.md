# ADR-031: QR codes and lot signs

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-11

## Context

The plan has `/q/{code}` redirects and a printable sign per lot, and printed signs must keep
working after a subdivision's slug is renamed (ADR-006, ADR-027). It doesn't say how codes are
made, how many a lot has, what a sign shows, or what an unlisted lot's code does.

## Decision

- **A code names a lot, not a URL.** `/q/{code}` asks public GraphQL (`qrTarget`) for the lot's
  current subdivision slug and number each time it's scanned, and redirects with a temporary
  307, so no browser remembers an old address.
- **One code per lot, made on first use.** Opening a lot's sign in the owner portal creates its
  code; it never changes after that. A unique index keeps it to one per lot. Codes are eight
  characters from lowercase letters and digits without look-alikes (0/o, 1/l/i), in case one
  is typed from a sign. Deleting a lot deletes its code.
- **Unlisted lots say so, and nothing else.** An unknown code, or the code of a lot that isn't
  published (or is in an unpublished subdivision), shows "This lot isn't listed right now",
  without saying which.
- **The sign shows only what doesn't change:** subdivision name, lot number, the QR code, the
  short URL (`cornerpin.app/q/…`), and "Scan for price, photos, documents and directions". Price
  and status change, and the code always opens the current page. It prints on one letter page;
  the page's header, breadcrumbs and buttons are hidden when printing.
- **The QR code** is generated on the server as SVG (the `qrcode` package) at error correction
  level Q, which still scans with about a quarter of it damaged, as outdoor signs get.
- **Testing reads the code from pixels.** Playwright screenshots the printed sign's QR code and
  decodes it with `jsqr`, follows it, renames the slug, and follows it again.

## Consequences

- A sign printed before a lot is published says "not listed" until the lot is published.
- Renaming a slug changes the lot's page address; links shared before the rename break, but
  signs don't.
- `/q/*` isn't kept for offline use (ADR-030): scanning offline shows the offline page.

## Related

ADR-006 (URLs), ADR-007 (GraphQL reads), ADR-027 (public pages), ADR-030 (offline)
