"""Seed the demo tenant with a synthetic subdivision. Idempotent: the demo tenant is deleted
(cascading to its rows) and recreated.

    uv run python -m cornerpin.seed

Runs as the owner role (DATABASE_URL). Everything here is synthetic; the place, prices and
homes are invented.
"""

import math
from dataclasses import dataclass
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, create_engine, text

from cornerpin.core.config import get_settings

DEMO_TENANT_ID = uuid5(NAMESPACE_URL, "https://cornerpin.app/tenants/demo")
DEMO_OWNER_EMAIL = "owner@demo.cornerpin.test"
DEMO_SLUG = "juniper-bench"

# South-west corner of the lot grid: open farmland south of Kuna, Idaho.
ORIGIN_LAT = 43.4005
ORIGIN_LON = -116.3880
LOT_WIDTH_M = 62.0
LOT_DEPTH_M = 70.0
STREET_M = 18.0
METERS_PER_DEGREE_LAT = 111_132.0


@dataclass(frozen=True)
class PhaseSpec:
    name: str
    released: bool
    rows: int
    cols: int


PHASES = (
    PhaseSpec("Phase 1", released=True, rows=3, cols=5),
    PhaseSpec("Phase 2", released=False, rows=2, cols=5),
)

SOLD = {3, 9, 14}
ON_HOLD = {5, 11}
HOMES = {
    7: {"bedrooms": 4, "bathrooms": Decimal("3.0"), "square_feet": 2650, "price": 549_000},
    8: {"bedrooms": 3, "bathrooms": Decimal("2.5"), "square_feet": 2180, "price": 489_000},
}


def lot_polygon_wkt(row: int, col: int) -> str:
    """A rectangular lot as WKT; each row of lots fronts its own street."""
    meters_per_degree_lon = METERS_PER_DEGREE_LAT * math.cos(math.radians(ORIGIN_LAT))
    south = row * (LOT_DEPTH_M + STREET_M)
    west = col * LOT_WIDTH_M
    corners_m = [
        (west, south),
        (west + LOT_WIDTH_M, south),
        (west + LOT_WIDTH_M, south + LOT_DEPTH_M),
        (west, south + LOT_DEPTH_M),
        (west, south),
    ]
    points = ", ".join(
        f"{ORIGIN_LON + x / meters_per_degree_lon:.7f} {ORIGIN_LAT + y / METERS_PER_DEGREE_LAT:.7f}"
        for x, y in corners_m
    )
    return f"MULTIPOLYGON((({points})))"


def land_price(number: int) -> int:
    return 84_000 + (number % 5) * 3_500 + (number // 5) * 2_000


def seed(conn: Connection, owner_email: str = DEMO_OWNER_EMAIL) -> UUID:
    """Rebuild the demo tenant from scratch. `owner_email` is its owner: the .test address
    locally, a real one in production (`python -m cornerpin.ops seed-demo`)."""
    # Buyer records block deleting their lot (migration 0004), so clear them first.
    for table in ("inquiries", "hold_requests"):
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
                "A synthetic demo subdivision: one-acre lots with power and water at the street,"
                " and two showcase homes."
            ),
        },
    ).scalar_one()

    number = 0
    row_offset = 0
    for order, spec in enumerate(PHASES):
        phase_id = conn.execute(
            text(
                "INSERT INTO phases (tenant_id, subdivision_id, name, sort_order, release_status)"
                " VALUES (:t, :s, :name, :order, :status) RETURNING id"
            ),
            {
                "t": DEMO_TENANT_ID,
                "s": subdivision_id,
                "name": spec.name,
                "order": order,
                "status": "released" if spec.released else "upcoming",
            },
        ).scalar_one()
        for row in range(spec.rows):
            for col in range(spec.cols):
                number += 1
                home = HOMES.get(number) if spec.released else None
                status = (
                    "sold" if number in SOLD else "on_hold" if number in ON_HOLD else "available"
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
                        "p": phase_id,
                        "number": str(number),
                        "wkt": lot_polygon_wkt(row_offset + row, col),
                        "price": (home["price"] if home else land_price(number))
                        if spec.released
                        else None,
                        "status": status if spec.released else "available",
                        "listing": "lot_and_home" if home else "land_only",
                        "bedrooms": home["bedrooms"] if home else None,
                        "bathrooms": home["bathrooms"] if home else None,
                        "square_feet": home["square_feet"] if home else None,
                        "home_description": "Showcase home, nearly finished." if home else None,
                        "published": spec.released,
                    },
                )
        row_offset += spec.rows

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
