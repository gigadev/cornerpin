"""Seed the demo tenant with a synthetic subdivision. Idempotent: the demo tenant is deleted
(cascading to its rows) and recreated.

    uv run python -m cornerpin.seed

Runs as the owner role (DATABASE_URL). Everything here is synthetic; the place, layout,
prices and homes are invented.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, create_engine, text

from cornerpin.core.config import get_settings
from cornerpin.financing.demo import seed_financing

DEMO_TENANT_ID = uuid5(NAMESPACE_URL, "https://cornerpin.app/tenants/demo")
DEMO_OWNER_EMAIL = "owner@demo.cornerpin.test"
DEMO_SLUG = "juniper-bench"

# The layout is modelled on a typical Treasure Valley plat (ADR-034): numbered blocks of
# homesites back to back along streets, a curved corner with wedge-shaped lots, and a second
# phase continuing each block east. Lots are numbered block-lot, so "3-9" is lot 9 of block 3.
# Coordinates are metres east and north of ORIGIN, the south-west corner of block 2, on
# farmland south of Kuna, Idaho.
ORIGIN_LAT = 43.4005
ORIGIN_LON = -116.3880
METERS_PER_DEGREE_LAT = 111_132.0
LOT_WIDTH_M = 20.0
LOT_DEPTH_M = 35.0
STREET_M = 16.0

PHASE_NAMES = ("Phase 1", "Phase 2")  # phase 1 released and published; phase 2 upcoming

Point = tuple[float, float]


@dataclass(frozen=True)
class LotSpec:
    number: str
    phase: int  # index into PHASE_NAMES
    corners: tuple[Point, ...]  # metres; lot_polygon_wkt closes the ring


def _rectangle(x: float, y: float, width: float, depth: float) -> tuple[Point, ...]:
    return ((x, y), (x + width, y), (x + width, y + depth), (x, y + depth))


def _row(block: int, first: int, count: int, x: float, y: float, phase: int) -> list[LotSpec]:
    """`count` lots side by side, west to east, from (x, y)."""
    return [
        LotSpec(
            f"{block}-{first + i}",
            phase,
            _rectangle(x + i * LOT_WIDTH_M, y, LOT_WIDTH_M, LOT_DEPTH_M),
        )
        for i in range(count)
    ]


def _arc(start_deg: float, end_deg: float, steps: int = 8) -> list[Point]:
    """The street's curved edge at block 3's corner, centred on block 2's south-west corner."""
    angles = [math.radians(start_deg + (end_deg - start_deg) * i / steps) for i in range(steps + 1)]
    return [(STREET_M * math.cos(a), STREET_M * math.sin(a)) for a in angles]


def _layout() -> tuple[LotSpec, ...]:
    back = -STREET_M - LOT_DEPTH_M  # block 3's rear lot line, west and south
    east = 6 * LOT_WIDTH_M  # where phase 2 starts
    north = 2 * LOT_DEPTH_M + STREET_M  # block 4's front lot line
    lots: list[LotSpec] = []
    # Block 2: two rows back to back between the two east-west streets.
    lots += _row(2, 1, 6, 0, LOT_DEPTH_M, 0)
    lots += _row(2, 7, 6, 0, 0, 0)
    lots += _row(2, 13, 4, east, LOT_DEPTH_M, 1)
    lots += _row(2, 17, 4, east, 0, 1)
    # Block 4: across the northern street, backing onto open space.
    lots += _row(4, 1, 6, 0, north, 0)
    lots += _row(4, 7, 4, east, north, 1)
    # Block 3: a column of lots facing east across the western street, two wedge lots around
    # the curved corner, then a row facing north across the southern street.
    lots.append(LotSpec("3-3", 0, _rectangle(back, 90, LOT_DEPTH_M, 22)))
    for n in range(4, 9):
        lots.append(LotSpec(f"3-{n}", 0, _rectangle(back, 90 - 18 * (n - 3), LOT_DEPTH_M, 18)))
    lots.append(LotSpec("3-9", 0, ((back, 0), *_arc(180, 225), (back, back))))
    lots.append(LotSpec("3-10", 0, ((back, back), *_arc(225, 270), (0, back))))
    lots += _row(3, 11, 6, 0, back, 0)
    lots += _row(3, 17, 4, east, back, 1)
    return tuple(lots)


LOTS = _layout()
SOLD = {"2-1", "2-2", "2-7", "2-8", "2-9", "3-9", "3-11", "3-12", "3-13", "4-1", "4-2", "4-3"}
ON_HOLD = {"2-3", "3-14", "4-4"}
HOMES = {
    "2-5": {"bedrooms": 4, "bathrooms": Decimal("3.0"), "square_feet": 2650, "price": 549_000,
            "description": "Showcase home, nearly finished."},
    "2-6": {"bedrooms": 3, "bathrooms": Decimal("2.5"), "square_feet": 2180, "price": 489_000,
            "description": "Showcase home, nearly finished."},
    "3-15": {"bedrooms": 5, "bathrooms": Decimal("3.5"), "square_feet": 3060, "price": 629_000,
             "description": "Framed and under roof; finishes in the spring."},
}  # fmt: skip
OPEN_SPACE_BLOCK = 4
CORNER_LOTS = {"3-3", "3-9", "3-10"}


def _area_m2(corners: tuple[Point, ...]) -> float:
    pairs = zip(corners, (*corners[1:], corners[0]), strict=True)
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in pairs)) / 2


def land_price(lot: LotSpec) -> int:
    """Bigger lots cost more, with premiums for corners and open space; rounded to $500."""
    block, index = (int(part) for part in lot.number.split("-"))
    price = 88_000 + 30 * _area_m2(lot.corners) + (index % 3) * 1_500
    price += 4_000 if lot.number in CORNER_LOTS else 0
    price += 6_000 if block == OPEN_SPACE_BLOCK else 0
    return round(price / 500) * 500


def lot_polygon_wkt(corners: tuple[Point, ...]) -> str:
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(ORIGIN_LAT))
    points = ", ".join(
        f"{ORIGIN_LON + x / meters_per_degree_lon:.7f} {ORIGIN_LAT + y / METERS_PER_DEGREE_LAT:.7f}"
        for x, y in (*corners, corners[0])
    )
    return f"MULTIPOLYGON((({points})))"


LISTED_DAYS_AGO = {0: 600, 1: 120}  # by phase: phase 1 went up for sale about 20 months ago


def _give_lots_a_history(conn: Connection, subdivision_id: UUID) -> None:
    """A believable past for the owner dashboard (P3-07, ADR-051): phase 1 listed about 20 months
    ago, its sales spread over the last year, its holds in the last few weeks. Written straight
    into the history, not by changing lots, so no change notices are queued."""
    rows = conn.execute(
        text(
            "SELECT l.id, l.number, p.sort_order FROM lots l JOIN phases p ON p.id = l.phase_id"
            " WHERE l.subdivision_id = :s"
        ),
        {"s": subdivision_id},
    ).all()
    sold = sorted((r for r in rows if r.number in SOLD), key=lambda r: r.number)
    held = sorted((r for r in rows if r.number in ON_HOLD), key=lambda r: r.number)
    for row in rows:
        listed = f"{LISTED_DAYS_AGO[row.sort_order]} days"
        conn.execute(
            text("UPDATE lots SET created_at = now() - CAST(:ago AS interval) WHERE id = :id;"),
            {"id": row.id, "ago": listed},
        )
        for table in ("lot_status_history", "lot_price_history"):
            conn.execute(
                text(
                    f"UPDATE {table} SET changed_at = now() - CAST(:ago AS interval)"  # noqa: S608
                    " WHERE lot_id = :id"
                ),
                {"id": row.id, "ago": listed},
            )
    # Each lot's one history row already holds its final status; it gets a later date.
    changes = [(row, 12 + 31 * i + (7 * i) % 11) for i, row in enumerate(sold)]
    changes += [(row, 4 + 6 * i) for i, row in enumerate(held)]
    for row, days_ago in changes:
        # The lot went in as available on the day it was listed, and changed later.
        conn.execute(
            text(
                "UPDATE lot_status_history SET from_status = 'available',"
                " changed_at = now() - make_interval(days => :days) WHERE lot_id = :id"
            ),
            {"id": row.id, "days": days_ago},
        )
        conn.execute(
            text(
                "INSERT INTO lot_status_history (tenant_id, lot_id, from_status, to_status,"
                " changed_at) SELECT tenant_id, id, NULL, 'available', created_at FROM lots"
                " WHERE id = :id"
            ),
            {"id": row.id},
        )


def seed(conn: Connection, owner_email: str = DEMO_OWNER_EMAIL) -> UUID:
    """Rebuild the demo tenant from scratch. `owner_email` is its owner: the .test address
    locally, a real one in production (`python -m cornerpin.ops seed-demo`)."""
    # Buyer records and financing applications block deleting their lot (migrations 0004, 0019),
    # so clear them first.
    for table in ("inquiries", "hold_requests", "financing_applications"):
        conn.execute(text(f"DELETE FROM {table} WHERE tenant_id = :id"), {"id": DEMO_TENANT_ID})  # noqa: S608
    conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": DEMO_TENANT_ID})
    conn.execute(
        text("INSERT INTO tenants (id, name, is_demo) VALUES (:id, 'Demo Land Co.', true)"),
        {"id": DEMO_TENANT_ID},
    )
    owner_id = conn.execute(
        text(
            "INSERT INTO users (email, display_name, time_zone) "
            "VALUES (:email, 'Demo Owner', 'America/Boise') "
            "ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name "
            "RETURNING id"
        ),
        {"email": owner_email},
    ).scalar_one()
    conn.execute(
        text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
        {"t": DEMO_TENANT_ID, "u": owner_id},
    )
    subdivision_id = conn.execute(
        text(
            "INSERT INTO subdivisions (tenant_id, name, slug, location, time_zone, description,"
            " published) VALUES (:t, 'Juniper Bench', :slug,"
            " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 'America/Boise', :description, true)"
            " RETURNING id"
        ),
        {
            "t": DEMO_TENANT_ID,
            "slug": DEMO_SLUG,
            "lon": ORIGIN_LON,
            "lat": ORIGIN_LAT,
            "description": (
                "A demo subdivision with invented lots, prices and homes: three blocks of"
                " homesites on curving streets, with more coming in phase 2. Lots are numbered"
                " block-lot, so 3-9 is lot 9 in block 3."
            ),
        },
    ).scalar_one()

    phase_ids = [
        conn.execute(
            text(
                "INSERT INTO phases (tenant_id, subdivision_id, name, sort_order, release_status)"
                " VALUES (:t, :s, :name, :order, :status) RETURNING id"
            ),
            {
                "t": DEMO_TENANT_ID,
                "s": subdivision_id,
                "name": name,
                "order": order,
                "status": "released" if order == 0 else "upcoming",
            },
        ).scalar_one()
        for order, name in enumerate(PHASE_NAMES)
    ]
    for lot in LOTS:
        released = lot.phase == 0
        home = HOMES.get(lot.number) if released else None
        status = (
            "sold" if lot.number in SOLD else "on_hold" if lot.number in ON_HOLD else "available"
        )
        conn.execute(
            text(
                "INSERT INTO lots (tenant_id, subdivision_id, phase_id, number, boundary,"
                " price, status, listing_type, home_bedrooms, home_bathrooms,"
                " home_square_feet, home_description, published) VALUES (:t, :s, :p,"
                " :number, ST_GeomFromText(:wkt, 4326), :price, :status, :listing,"
                " :bedrooms, :bathrooms, :square_feet, :home_description, :published)"
            ),
            {
                "t": DEMO_TENANT_ID,
                "s": subdivision_id,
                "p": phase_ids[lot.phase],
                "number": lot.number,
                "wkt": lot_polygon_wkt(lot.corners),
                "price": (home["price"] if home else land_price(lot)) if released else None,
                "status": status if released else "available",
                "listing": "lot_and_home" if home else "land_only",
                "bedrooms": home["bedrooms"] if home else None,
                "bathrooms": home["bathrooms"] if home else None,
                "square_feet": home["square_feet"] if home else None,
                "home_description": home["description"] if home else None,
                "published": released,
            },
        )

    _give_lots_a_history(conn, subdivision_id)

    # Acreage and the subdivision outline come from the lot shapes.
    conn.execute(
        text(
            "UPDATE lots SET acreage = round((ST_Area(boundary::geography) / 4046.8564224)"
            "::numeric, 3) WHERE subdivision_id = :s"
        ),
        {"s": subdivision_id},
    )
    conn.execute(
        text(
            "UPDATE subdivisions SET boundary = (SELECT ST_Multi(ST_ConvexHull(ST_Collect("
            "boundary))) FROM lots WHERE subdivision_id = :s),"
            " location = (SELECT ST_Centroid(ST_Collect(boundary)) FROM lots"
            " WHERE subdivision_id = :s) WHERE id = :s"
        ),
        {"s": subdivision_id},
    )
    # The demo tenant alone has the synthetic owner-financing module (ADR-013, ADR-049).
    seed_financing(conn, DEMO_TENANT_ID)
    return subdivision_id


def main() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        seed(conn)
        lots = conn.execute(
            text("SELECT count(*) FROM lots WHERE tenant_id = :t"), {"t": DEMO_TENANT_ID}
        ).scalar_one()
    print(f"Seeded demo tenant: /{DEMO_SLUG} with {lots} lots; owner {DEMO_OWNER_EMAIL}")


if __name__ == "__main__":
    main()
