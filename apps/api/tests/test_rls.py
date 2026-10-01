"""Row-level security (ADR-003, ADR-021). P1-02 acceptance: a cross-tenant read returns 0 rows
for every tenant-owned table. Tables are discovered from the catalog, so a new table with a
tenant_id column is covered automatically and must ship with policies and fixture rows."""

from uuid import UUID

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from cornerpin.core.db import public_session, user_session

from .conftest import Databases, TenantData

IGNORED_TABLES = {"alembic_version", "spatial_ref_sys"}


def _tables(engine: Engine, with_column: str | None = None) -> list[str]:
    sql = """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND (CAST(:column AS text) IS NULL OR EXISTS (
            SELECT 1 FROM pg_attribute a
            WHERE a.attrelid = c.oid AND a.attname = :column AND NOT a.attisdropped))
        ORDER BY c.relname
    """
    with engine.connect() as conn:
        names = conn.execute(text(sql), {"column": with_column}).scalars().all()
    return [name for name in names if name not in IGNORED_TABLES]


def _count(session: Session, table: str, tenant_id: UUID) -> int:
    count: int = session.execute(
        text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"),  # noqa: S608
        {"t": tenant_id},
    ).scalar_one()
    return count


class Rollback(Exception):
    """Raised to roll back a session that changed data."""


# --- every table is covered ---------------------------------------------------------------


def test_every_table_has_rls_enabled_and_forced(db: Databases) -> None:
    sql = """
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
          AND NOT (c.relrowsecurity AND c.relforcerowsecurity)
    """
    with db.owner.connect() as conn:
        missing = set(conn.execute(text(sql)).scalars().all()) - IGNORED_TABLES
    assert missing == set()


def test_tenant_owned_tables_are_discovered(db: Databases) -> None:
    tables = _tables(db.owner, with_column="tenant_id")
    assert {"subdivisions", "lots", "inquiries", "contact_consents"} <= set(tables)


# --- cross-tenant reads (P1-02 acceptance) -------------------------------------------------


def test_cross_tenant_reads_return_zero_rows(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    tables = _tables(db.owner, with_column="tenant_id")
    assert tables, "no tenant-owned tables found"

    with user_session(bravo.owner_id, bravo.tenant_id, engine=db.api) as session:
        own = {table: _count(session, table, bravo.tenant_id) for table in tables}
    empty = [table for table, n in own.items() if n == 0]
    assert empty == [], f"fixture rows missing, so isolation is untested for: {empty}"

    with user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session:
        leaked = {table: _count(session, table, bravo.tenant_id) for table in tables}
    assert leaked == dict.fromkeys(tables, 0)


def test_owner_sees_only_own_tenant(db: Databases, tenants: tuple[TenantData, TenantData]) -> None:
    alpha, _ = tenants
    with user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session:
        tenant_ids = session.execute(text("SELECT id FROM tenants")).scalars().all()
        lot_tenants = session.execute(text("SELECT DISTINCT tenant_id FROM lots")).scalars().all()
    assert tenant_ids == [alpha.tenant_id]
    assert lot_tenants == [alpha.tenant_id]


def test_claimed_tenant_without_membership_sees_nothing(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    """A bug that sets another tenant's id still leaks nothing: membership is checked in SQL."""
    alpha, bravo = tenants
    tables = _tables(db.owner, with_column="tenant_id")
    with user_session(alpha.owner_id, bravo.tenant_id, engine=db.api) as session:
        visible = {table: _count(session, table, bravo.tenant_id) for table in tables}
    assert visible == dict.fromkeys(tables, 0)


def test_users_see_only_themselves(db: Databases, tenants: tuple[TenantData, TenantData]) -> None:
    alpha, _ = tenants
    with user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session:
        user_ids = session.execute(text("SELECT id FROM users")).scalars().all()
        prefs = session.execute(text("SELECT count(*) FROM notification_prefs")).scalar_one()
        subscriptions = session.execute(
            text("SELECT count(*) FROM push_subscriptions")
        ).scalar_one()
    assert user_ids == [alpha.owner_id]
    assert prefs == 0
    assert subscriptions == 0


# --- buyers --------------------------------------------------------------------------------


def test_buyer_sees_own_activity_and_nothing_else(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    with user_session(alpha.buyer_id, engine=db.api) as session:
        inquiries = session.execute(text("SELECT user_id FROM inquiries")).scalars().all()
        saved = session.execute(text("SELECT user_id FROM saved_lots")).scalars().all()
        drafts = session.execute(text("SELECT count(*) FROM lots")).scalar_one()
        other = _count(session, "inquiries", bravo.tenant_id)
    assert inquiries == [alpha.buyer_id]
    assert saved == [alpha.buyer_id]
    assert drafts == 0  # a buyer has no tenant; listings come through public_session
    assert other == 0


# --- writes --------------------------------------------------------------------------------


def test_cannot_write_into_another_tenant(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
    ):
        session.execute(
            text(
                "INSERT INTO subdivisions (tenant_id, name, slug, location, time_zone)"
                " VALUES (:t, 'x', 'sneaky', ST_MakePoint(0, 0)::geometry(Point, 4326), 'UTC')"
            ),
            {"t": bravo.tenant_id},
        )


def test_cannot_update_another_tenants_lot(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    with (
        pytest.raises(Rollback),
        user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
    ):
        updated = session.execute(
            text("UPDATE lots SET status = 'sold' WHERE id = :id RETURNING id"),
            {"id": bravo.lot_id},
        ).all()
        assert updated == []
        raise Rollback


def test_tenant_id_must_match_the_lot(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    """A buyer row cannot be filed under a different tenant than its lot."""
    alpha, bravo = tenants
    with (
        pytest.raises(DBAPIError, match="foreign key"),
        user_session(alpha.buyer_id, engine=db.api) as session,
    ):
        session.execute(
            text("INSERT INTO saved_lots (user_id, lot_id, tenant_id) VALUES (:u, :l, :t)"),
            {"u": alpha.buyer_id, "l": bravo.lot_id, "t": alpha.tenant_id},
        )


def test_consents_are_append_only(db: Databases, tenants: tuple[TenantData, TenantData]) -> None:
    alpha, _ = tenants
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        user_session(alpha.buyer_id, engine=db.api) as session,
    ):
        session.execute(text("UPDATE contact_consents SET granted = false"))


def test_status_and_price_changes_are_recorded(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    with (
        pytest.raises(Rollback),
        user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
    ):
        session.execute(
            text("UPDATE lots SET status = 'on_hold', price = 95000 WHERE id = :id"),
            {"id": alpha.lot_id},
        )
        status = session.execute(
            text(
                "SELECT from_status, to_status, changed_by FROM lot_status_history"
                " WHERE lot_id = :id ORDER BY changed_at DESC, from_status NULLS LAST LIMIT 1"
            ),
            {"id": alpha.lot_id},
        ).one()
        price = session.execute(
            text(
                "SELECT from_price, to_price, changed_by FROM lot_price_history"
                " WHERE lot_id = :id AND from_price IS NOT NULL"
            ),
            {"id": alpha.lot_id},
        ).one()
        assert tuple(status) == ("available", "on_hold", alpha.owner_id)
        assert (int(price[0]), int(price[1]), price[2]) == (100000, 95000, alpha.owner_id)
        raise Rollback


# --- public reads --------------------------------------------------------------------------


def test_public_sees_only_published_listings(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    with public_session(engine=db.api) as session:
        lots = set(session.execute(text("SELECT id FROM lots")).scalars().all())
        media = session.execute(text("SELECT storage_key FROM lot_media")).scalars().all()
    assert lots == {alpha.lot_id, bravo.lot_id}
    assert "hidden.jpg" not in media


def test_public_cannot_see_lots_of_unpublished_subdivisions(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    with db.owner.connect() as owner:
        # Unpublish, check from a separate public connection, then publish again.
        owner.execute(
            text("UPDATE subdivisions SET published = false WHERE id = :id"),
            {"id": alpha.subdivision_id},
        )
        owner.commit()
        try:
            with public_session(engine=db.api) as session:
                lots = set(session.execute(text("SELECT id FROM lots")).scalars().all())
                phases = session.execute(
                    text("SELECT count(*) FROM phases WHERE subdivision_id = :s"),
                    {"s": alpha.subdivision_id},
                ).scalar_one()
            assert alpha.lot_id not in lots
            assert phases == 0
        finally:
            owner.execute(
                text("UPDATE subdivisions SET published = true WHERE id = :id"),
                {"id": alpha.subdivision_id},
            )
            owner.commit()


@pytest.mark.parametrize(
    "table",
    [
        "inquiries",
        "hold_requests",
        "saved_lots",
        "contact_consents",
        "users",
        "memberships",
        "tenants",
        "lot_status_history",
        "lot_price_history",
    ],
)
def test_public_cannot_read_private_tables(db: Databases, table: str) -> None:
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        public_session(engine=db.api) as session,
    ):
        session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))  # noqa: S608


def test_public_cannot_write(db: Databases, tenants: tuple[TenantData, TenantData]) -> None:
    alpha, _ = tenants
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        public_session(engine=db.api) as session,
    ):
        session.execute(text("UPDATE lots SET price = 1 WHERE id = :id"), {"id": alpha.lot_id})


# --- the login role itself -----------------------------------------------------------------


def test_login_role_without_set_role_has_no_access(db: Databases) -> None:
    with db.api.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text("SELECT 1 FROM lots LIMIT 1"))


def test_api_role_is_not_owner_or_superuser(db: Databases) -> None:
    with db.api.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolinherit FROM pg_roles"
                " WHERE rolname = current_user"
            )
        ).one()
        owns = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE tableowner = current_user")
        ).scalar_one()
    assert tuple(row) == (False, False, False)
    assert owns == 0
