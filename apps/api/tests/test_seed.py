from sqlalchemy import text

from cornerpin.seed import DEMO_TENANT_ID, PHASES, seed

from .conftest import Databases


def test_seed_builds_demo_subdivision_and_is_repeatable(db: Databases) -> None:
    with db.owner.connect() as conn:
        seed(conn)
        subdivision_id = seed(conn)  # a second run replaces the first

        expected_lots = sum(spec.rows * spec.cols for spec in PHASES)
        expected_published = sum(spec.rows * spec.cols for spec in PHASES if spec.released)
        row = conn.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE published),"
                " count(*) FILTER (WHERE acreage IS NULL OR boundary IS NULL),"
                " count(*) FILTER (WHERE listing_type = 'lot_and_home')"
                " FROM lots WHERE tenant_id = :t"
            ),
            {"t": DEMO_TENANT_ID},
        ).one()
        overlaps = conn.execute(
            text(
                "SELECT count(*) FROM lots a JOIN lots b ON a.id < b.id"
                " AND a.subdivision_id = b.subdivision_id"
                " AND ST_Overlaps(a.boundary, b.boundary) WHERE a.subdivision_id = :s"
            ),
            {"s": subdivision_id},
        ).scalar_one()
        history = conn.execute(
            text("SELECT count(*) FROM lot_status_history WHERE tenant_id = :t"),
            {"t": DEMO_TENANT_ID},
        ).scalar_one()
        conn.rollback()

    assert tuple(row) == (expected_lots, expected_published, 0, 2)
    assert overlaps == 0
    assert history == expected_lots
