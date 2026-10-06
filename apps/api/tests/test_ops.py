"""P1-12: operations commands. They must work when the owner role is not a superuser and can't
bypass row-level security, as on Neon, and leave RLS forced afterwards."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from cornerpin import ops
from cornerpin.core.config import REPO_ROOT, get_settings
from cornerpin.seed import DEMO_SLUG

from .conftest import TEST_API_URL, TEST_OWNER_URL, Databases, build_tenant

OPS_DATABASE = "cornerpin_ops"
OPS_OWNER = "cornerpin_ops_owner"
APP_ROLES = (
    "cornerpin_user, cornerpin_public, cornerpin_api, cornerpin_auth, cornerpin_worker,"
    " cornerpin_leads"
)


@pytest.fixture(scope="module")
def neon_like(db: Databases) -> Iterator[URL]:
    """A database owned by a role that is neither superuser nor BYPASSRLS, with PostGIS
    already available, as a managed Postgres provides it."""
    admin = create_engine(TEST_OWNER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {OPS_DATABASE} WITH (FORCE)"))
        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": OPS_OWNER}
        ).scalar()
        if not exists:
            conn.execute(text(f"CREATE ROLE {OPS_OWNER} LOGIN CREATEROLE PASSWORD '{OPS_OWNER}'"))
        # The app's roles already exist in this cluster (other test databases made them); on a
        # fresh managed database the owner would create them, and so administer them without
        # being able to act as them (Postgres 16+). Grant exactly that; granting again updates
        # the options of an earlier run's grant.
        conn.execute(
            text(f"GRANT {APP_ROLES} TO {OPS_OWNER} WITH ADMIN TRUE, INHERIT FALSE, SET FALSE")
        )
        conn.execute(text(f"CREATE DATABASE {OPS_DATABASE} OWNER {OPS_OWNER}"))
    admin.dispose()
    superuser = create_engine(TEST_OWNER_URL.set(database=OPS_DATABASE))
    with superuser.begin() as conn:
        conn.execute(text("CREATE EXTENSION postgis; CREATE EXTENSION citext"))
    superuser.dispose()
    yield TEST_OWNER_URL.set(database=OPS_DATABASE, username=OPS_OWNER, password=OPS_OWNER)


@pytest.fixture
def ops_env(neon_like: URL, monkeypatch: pytest.MonkeyPatch) -> Iterator[URL]:
    monkeypatch.setenv("DATABASE_URL", neon_like.render_as_string(hide_password=False))
    monkeypatch.setenv(
        "API_DATABASE_URL",
        TEST_API_URL.set(database=OPS_DATABASE).render_as_string(hide_password=False),
    )
    get_settings.cache_clear()
    yield neon_like
    get_settings.cache_clear()


def forced_tables(url: URL) -> set[str]:
    engine = create_engine(url)
    with engine.connect() as conn:
        names = set(
            conn.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity"
                )
            ).scalars()
        )
    engine.dispose()
    return names


def test_migrate_seed_and_create_a_tenant_as_a_plain_owner(
    ops_env: URL, capsys: pytest.CaptureFixture[str]
) -> None:
    # Production had buyer activity before leads existed (P2-01): migrate to just before them,
    # add some, then the rest of the way, and the activity becomes leads.
    command.upgrade(Config(str(REPO_ROOT / "alembic.ini")), "0010")
    superuser = create_engine(TEST_OWNER_URL.set(database=OPS_DATABASE))
    with superuser.begin() as conn:
        earlier = build_tenant(conn, "earlier")
        conn.execute(
            text(
                "INSERT INTO inquiries (tenant_id, lot_id, name, email, message)"
                " VALUES (:t, :l, 'Walk-in', 'walkin@example.test', 'Still available?')"
            ),
            {"t": earlier.tenant_id, "l": earlier.lot_id},
        )
        conn.execute(
            text(
                "UPDATE hold_requests SET status = 'approved', decided_by = :o,"
                " decided_at = now() + interval '1 minute' WHERE tenant_id = :t"
            ),
            {"t": earlier.tenant_id, "o": earlier.owner_id},
        )
    ops.migrate()
    with superuser.connect() as conn:
        leads = conn.execute(
            text(
                "SELECT l.email::text, l.stage::text, l.user_id IS NOT NULL,"
                " array_agg(e.kind::text ORDER BY e.created_at, e.kind::text)"
                " FROM leads l JOIN lead_events e ON e.lead_id = l.id WHERE l.tenant_id = :t"
                " GROUP BY l.id ORDER BY l.email"
            ),
            {"t": earlier.tenant_id},
        ).all()
    assert [tuple(lead) for lead in leads] == [
        ("buyer@earlier.test", "holding", True,
         ["consent_changed", "hold_requested", "inquiry", "hold_approved"]),
        ("walkin@example.test", "new", False, ["inquiry"]),
    ]  # fmt: skip
    forced = forced_tables(ops_env)
    assert {"lots", "tenants", "memberships", "contact_consents"} <= forced

    ops.check()
    report = capsys.readouterr().out
    assert "owner bypasses RLS: False" in report
    head = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini"))).get_current_head()
    assert f"migration: {head}" in report

    ops.seed_demo("demo-owner@example.test")
    tenant_id = ops.create_tenant("Ricky's Land Co.", "ricky@example.test", "Ricky")
    with pytest.raises(SystemExit, match="already exists"):
        ops.create_tenant("ricky's land co.", "someone@example.test", None)

    assert forced_tables(ops_env) == forced  # RLS is forced again afterwards
    with superuser.connect() as conn:
        lots = conn.execute(
            text(
                "SELECT count(*) FROM lots l JOIN subdivisions s ON s.id = l.subdivision_id"
                " WHERE s.slug = :slug"
            ),
            {"slug": DEMO_SLUG},
        ).scalar_one()
        owner = conn.execute(
            text(
                "SELECT u.email, u.display_name, u.email_verified_at IS NULL, m.role::text"
                " FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.tenant_id = :t"
            ),
            {"t": tenant_id},
        ).one()
    superuser.dispose()
    assert lots > 0
    assert tuple(owner) == ("ricky@example.test", "Ricky", True, "owner")


def test_migrate_needs_an_api_role_password(ops_env: URL, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_DATABASE_URL", "postgresql+psycopg://someone@localhost/x")
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="cornerpin_api"):
        ops.migrate()
