"""Operations commands for a deployed database (ADR-032). They connect as the owner role
(DATABASE_URL) and run as Cloud Run jobs from the API image, or locally:

    uv run python -m cornerpin.ops check
    uv run python -m cornerpin.ops migrate
    uv run python -m cornerpin.ops seed-demo --owner-email you@example.com
    uv run python -m cornerpin.ops create-tenant --name "Land Co." --owner-email owner@example.com

Every tenant-owned table has row-level security forced on, which applies to the owner too unless
it is a superuser or has BYPASSRLS. Locally the owner is a superuser; on Neon it may not be, so
commands that write tenant rows lift the forcing inside their own transaction and put it back
before committing (other sessions never see it lifted).
"""

import argparse
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from uuid import UUID

from psycopg import sql
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

from cornerpin.core.config import REPO_ROOT, get_settings
from cornerpin.core.fields import normalize_email
from cornerpin.seed import DEMO_TENANT_ID, seed


def owner_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def bypasses_rls(conn: Connection) -> bool:
    row = conn.execute(
        text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
    ).one()
    return bool(row.rolsuper or row.rolbypassrls)


@contextmanager
def owner_writes(conn: Connection) -> Generator[None]:
    """Let the owner write tenant rows for the rest of this transaction."""
    if bypasses_rls(conn):
        yield
        return
    tables: Sequence[str] = (
        conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity"
            )
        )
        .scalars()
        .all()
    )
    for table in tables:
        conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
    yield
    for table in tables:
        conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def check() -> None:
    """What a deploy depends on, printed for a person to read."""
    with owner_engine().connect() as conn:
        facts = {
            "database": conn.execute(text("SELECT current_database()")).scalar_one(),
            "owner role": conn.execute(text("SELECT current_user")).scalar_one(),
            "owner bypasses RLS": bypasses_rls(conn),
            "postgres": conn.execute(text("SHOW server_version")).scalar_one(),
            "postgis available": conn.execute(
                text("SELECT default_version FROM pg_available_extensions WHERE name = 'postgis'")
            ).scalar_one_or_none(),
            "migration": conn.execute(
                text(
                    "SELECT CASE WHEN to_regclass('alembic_version') IS NULL THEN NULL"
                    " ELSE (SELECT version_num FROM alembic_version) END"
                )
            ).scalar_one_or_none(),
        }
    for name, value in facts.items():
        print(f"{name}: {value}")


def migrate() -> None:
    """Apply migrations, then give cornerpin_api the password in API_DATABASE_URL (in the cloud
    the role's password comes from Secret Manager, not from a migration)."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(REPO_ROOT / "alembic.ini")), "head")
    url = make_url(get_settings().api_database_url)
    if url.username != "cornerpin_api" or not url.password:
        raise SystemExit("API_DATABASE_URL must log in as cornerpin_api with a password")
    statement = sql.SQL("ALTER ROLE cornerpin_api PASSWORD {}").format(sql.Literal(url.password))
    with owner_engine().begin() as conn:
        conn.exec_driver_sql(statement.as_string())
    print("migrated; cornerpin_api password set")


def seed_demo(owner_email: str) -> None:
    """Rebuild the demo tenant (Juniper Bench) with `owner_email` as its owner."""
    with owner_engine().begin() as conn, owner_writes(conn):
        subdivision_id = seed(conn, owner_email=owner_email)
    print(f"demo tenant {DEMO_TENANT_ID}, subdivision {subdivision_id}; owner {owner_email}")


def create_tenant(name: str, owner_email: str, owner_name: str | None) -> UUID:
    """A new tenant with one owner. The owner signs in with an emailed link to that address;
    the account is created now, unverified, and verified by that first sign-in."""
    with owner_engine().begin() as conn, owner_writes(conn):
        existing = conn.execute(
            text("SELECT id FROM tenants WHERE lower(name) = lower(:name)"), {"name": name}
        ).scalar_one_or_none()
        if existing:
            raise SystemExit(f"a tenant named {name!r} already exists: {existing}")
        tenant_id: UUID = conn.execute(
            text("INSERT INTO tenants (name) VALUES (:name) RETURNING id"), {"name": name}
        ).scalar_one()
        user_id = conn.execute(
            text(
                "INSERT INTO users (email, display_name) VALUES (:email, :name)"
                " ON CONFLICT (email) DO UPDATE"
                " SET display_name = coalesce(users.display_name, EXCLUDED.display_name)"
                " RETURNING id"
            ),
            {"email": owner_email, "name": owner_name},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
            {"t": tenant_id, "u": user_id},
        )
    print(f"tenant {name!r}: {tenant_id}; owner {owner_email}")
    return tenant_id


def main(argv: Sequence[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m cornerpin.ops")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="print what a deploy depends on")
    commands.add_parser("migrate", help="apply migrations and set the API role's password")
    demo = commands.add_parser("seed-demo", help="rebuild the demo tenant")
    demo.add_argument("--owner-email", required=True)
    tenant = commands.add_parser("create-tenant", help="create a tenant with one owner")
    tenant.add_argument("--name", required=True)
    tenant.add_argument("--owner-email", required=True)
    tenant.add_argument("--owner-name")
    args = parser.parse_args(argv)

    if args.command == "check":
        check()
    elif args.command == "migrate":
        migrate()
    elif args.command == "seed-demo":
        seed_demo(normalize_email(args.owner_email))
    elif args.command == "create-tenant":
        create_tenant(args.name.strip(), normalize_email(args.owner_email), args.owner_name)


if __name__ == "__main__":
    main(sys.argv[1:])
