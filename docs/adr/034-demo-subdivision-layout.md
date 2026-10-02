# ADR-034: A realistic demo subdivision, and lot numbers in reading order

- **Status:** Accepted
- **Date:** 2026-10-02
- **Applies from:** P1-12 (before the demo is seeded in production)

## Context

The demo tenant is what visitors and reviewers see at cornerpin.app before Ricky's lots are
live, and the plan keeps it synthetic (ADR-013). The first seed was a grid of fifteen one-acre
squares, which reads as test data. Scott shared a real Treasure Valley builder's site plan as
the look to aim for, and agreed that copying a real subdivision would present someone else's
lots, prices and photos as listings on Cornerpin.

Real plats number lots by block ("Lot 9, Block 3", shown as 3-9). Lot lists sorted numbers
with a zero-padding rule that put 3-9 before 2-10.

## Decision

Scott chose on 2026-10-02 to model the demo on that plan's layout, with everything invented.

- **Juniper Bench keeps its name and address** (`/juniper-bench`), so links, the guide and the
  deploy smoke check stay valid.
- **The layout is plat-like:** blocks 2, 3 and 4 of suburban homesites (about 0.16–0.17 acres)
  back to back along streets, a curved corner with two wedge-shaped lots (about 0.3 acres), and
  a phase 2 continuing each block, unpublished. The lot shapes are generated in metres in
  `seed.py`, so the layout reads as code, not a list of coordinates.
- **Lots are numbered block-lot** (`2-5`, `3-9`). Statuses are spread the way a selling
  subdivision looks: about a third sold, a few on hold, the rest available. Three lots carry
  homes. Prices follow lot size, with premiums for corners and for lots backing onto open
  space.
- **Nothing real is reused:** no builder, street or subdivision names, photos or prices. The
  description says the lots, prices and homes are invented.
- **Lot numbers sort in reading order everywhere** through an ICU collation with numeric
  ordering (`lot_number`, migration 0010): 2 before 10, 2-9 before 2-10 before 3-1, numbers
  before letters. It replaces the zero-padding rule.

## Consequences

- Owners whose plats use block-lot numbers (likely including Ricky) get lists in the order
  they expect.
- Tests refer to demo lots through `DEMO_LOTS` in `apps/web/e2e/fixtures.ts`, kept in step
  with `seed.py` and `e2e_server.py`.
- Production needs ICU in Postgres, which Neon and the PostGIS image both have.
- The demo has no photos in production until someone uploads them in the portal.

## Related

ADR-013 (synthetic demo), ADR-026 (lot geometry), ADR-027 (public pages)
