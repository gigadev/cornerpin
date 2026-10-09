from sqlalchemy import text

from cornerpin.seed import DEMO_TENANT_ID, HOMES, LOTS, ON_HOLD, SOLD, seed

from .conftest import Databases


def test_seed_builds_demo_subdivision_and_is_repeatable(db: Databases) -> None:
    with db.owner.connect() as conn:
        seed(conn)
        subdivision_id = seed(conn)  # a second run replaces the first

        expected_published = sum(1 for lot in LOTS if lot.phase == 0)
        row = conn.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE published),"
                " count(*) FILTER (WHERE acreage IS NULL OR boundary IS NULL),"
                " count(*) FILTER (WHERE NOT ST_IsValid(boundary)),"
                " count(*) FILTER (WHERE listing_type = 'lot_and_home'),"
                " count(*) FILTER (WHERE published AND price IS NULL)"
                " FROM lots WHERE tenant_id = :t"
            ),
            {"t": DEMO_TENANT_ID},
        ).one()
        overlaps = conn.execute(
            text(
                "SELECT count(*) FROM lots a JOIN lots b ON a.id < b.id"
                " AND a.subdivision_id = b.subdivision_id"
                " AND ST_Relate(a.boundary, b.boundary, '2********') WHERE a.subdivision_id = :s"
            ),
            {"s": subdivision_id},
        ).scalar_one()
        # Suburban homesites, with the corner wedges the largest (ADR-034).
        acres = dict(
            conn.execute(
                text("SELECT number, acreage FROM lots WHERE subdivision_id = :s"),
                {"s": subdivision_id},
            ).all()
        )
        history = conn.execute(
            text("SELECT count(*) FROM lot_status_history WHERE tenant_id = :t"),
            {"t": DEMO_TENANT_ID},
        ).scalar_one()
        conn.rollback()

    assert tuple(row) == (len(LOTS), expected_published, 0, 0, len(HOMES), 0)
    assert overlaps == 0
    assert all(0.1 < float(value) < 0.4 for value in acres.values())
    assert max(acres, key=lambda number: acres[number]) in {"3-9", "3-10"}
    # Every lot was listed; the sold and held ones changed later (ADR-051).
    assert history == len(LOTS) + len(SOLD) + len(ON_HOLD)
