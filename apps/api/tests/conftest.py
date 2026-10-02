"""Database fixtures. Tests that use `db` get a fresh `cornerpin_test` database on the local
PostGIS container (docker compose up -d), migrated to head. Other tests need no database.

The settings are pointed at the test database before anything reads them, so code under test
that uses the default engines (the API, the outbox) also runs against it."""

import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.config import get_settings
from cornerpin.devtools import recreate_database
from cornerpin.main import create_app

TEST_DATABASE = "cornerpin_test"

_dev = get_settings()
TEST_OWNER_URL = make_url(_dev.database_url).set(database=TEST_DATABASE)
TEST_API_URL = make_url(_dev.api_database_url).set(database=TEST_DATABASE)
os.environ["DATABASE_URL"] = TEST_OWNER_URL.render_as_string(hide_password=False)
os.environ["API_DATABASE_URL"] = TEST_API_URL.render_as_string(hide_password=False)
os.environ["OUTBOX_RUNNER"] = "off"
# Uploaded files go to a throwaway folder, not the developer's var/storage.
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="cornerpin-test-storage-")
get_settings.cache_clear()


@dataclass(frozen=True)
class Databases:
    owner: Engine  # migrations and fixtures; superuser locally, so RLS does not apply
    api: Engine  # cornerpin_api, exactly as the API connects


@pytest.fixture(scope="session")
def db() -> Iterator[Databases]:
    try:
        recreate_database(TEST_OWNER_URL)
    except OperationalError as exc:
        pytest.fail(f"Postgres is not reachable; run `docker compose up -d` first ({exc})")

    owner = create_engine(TEST_OWNER_URL)
    api = create_engine(TEST_API_URL)
    yield Databases(owner=owner, api=api)
    owner.dispose()
    api.dispose()


@dataclass(frozen=True)
class TenantData:
    tenant_id: UUID
    owner_id: UUID
    buyer_id: UUID
    subdivision_id: UUID
    lot_id: UUID
    unpublished_lot_id: UUID


def _one(conn: Connection, sql: str, **params: object) -> UUID:
    value: UUID = conn.execute(text(sql), params).scalar_one()
    return value


def build_tenant(conn: Connection, label: str) -> TenantData:
    """A tenant with one row in every tenant-owned and user-owned table."""
    tenant_id = _one(conn, "INSERT INTO tenants (name) VALUES (:n) RETURNING id", n=label)
    owner_id = _one(
        conn,
        "INSERT INTO users (email) VALUES (:e) RETURNING id",
        e=f"owner@{label}.test",
    )
    buyer_id = _one(
        conn,
        "INSERT INTO users (email) VALUES (:e) RETURNING id",
        e=f"buyer@{label}.test",
    )
    conn.execute(
        text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
        {"t": tenant_id, "u": owner_id},
    )
    subdivision_id = _one(
        conn,
        "INSERT INTO subdivisions (tenant_id, name, slug, location, time_zone, published)"
        " VALUES (:t, :n, :s, ST_SetSRID(ST_MakePoint(-116.2, 43.6), 4326), 'America/Boise',"
        " true) RETURNING id",
        t=tenant_id,
        n=f"{label} subdivision",
        s=f"{label}-subdivision",
    )
    phase_id = _one(
        conn,
        "INSERT INTO phases (tenant_id, subdivision_id, name, release_status)"
        " VALUES (:t, :s, 'Phase 1', 'released') RETURNING id",
        t=tenant_id,
        s=subdivision_id,
    )
    lot_sql = (
        "INSERT INTO lots (tenant_id, subdivision_id, phase_id, number, price, published)"
        " VALUES (:t, :s, :p, :n, 100000, :pub) RETURNING id"
    )
    lot_id = _one(conn, lot_sql, t=tenant_id, s=subdivision_id, p=phase_id, n="1", pub=True)
    unpublished_lot_id = _one(
        conn, lot_sql, t=tenant_id, s=subdivision_id, p=phase_id, n="2", pub=False
    )
    params = {
        "t": tenant_id,
        "s": subdivision_id,
        "l": lot_id,
        "b": buyer_id,
        "u": unpublished_lot_id,
    }
    for sql in (
        "INSERT INTO lot_media (tenant_id, lot_id, storage_key, content_type)"
        " VALUES (:t, :l, 'photo.jpg', 'image/jpeg'), (:t, :u, 'hidden.jpg', 'image/jpeg')",
        "INSERT INTO lot_documents (tenant_id, lot_id, kind, title, storage_key, content_type,"
        " size_bytes) VALUES (:t, :l, 'plat', 'Plat', 'plat.pdf', 'application/pdf', 1)",
        "INSERT INTO qr_codes (code, tenant_id, lot_id)"
        " VALUES (substr(md5(CAST(:t AS text)), 1, 8), :t, :l)",
        "INSERT INTO saved_lots (user_id, lot_id, tenant_id) VALUES (:b, :l, :t)",
        "INSERT INTO inquiries (tenant_id, lot_id, user_id, name, email, message)"
        " VALUES (:t, :l, :b, 'Buyer', 'buyer@example.test', 'Is it still available?')",
        "INSERT INTO hold_requests (tenant_id, lot_id, user_id, name, email)"
        " VALUES (:t, :l, :b, 'Buyer', 'buyer@example.test')",
        "INSERT INTO contact_consents (tenant_id, user_id, channel, granted, source)"
        " VALUES (:t, :b, 'email', true, 'test')",
        "INSERT INTO notification_prefs (user_id) VALUES (:b)",
        "INSERT INTO subdivision_overlays (tenant_id, subdivision_id, storage_key, content_type,"
        " width, height, corners) VALUES (:t, :s, 'plat.png', 'image/png', 10, 10,"
        " '[[0,1],[1,1],[1,0],[0,0]]'::jsonb)",
        "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)"
        " VALUES (:b, 'https://push.example.test/' || CAST(:b AS text), 'key', 'auth')",
    ):
        conn.execute(text(sql), params)
    return TenantData(
        tenant_id=tenant_id,
        owner_id=owner_id,
        buyer_id=buyer_id,
        subdivision_id=subdivision_id,
        lot_id=lot_id,
        unpublished_lot_id=unpublished_lot_id,
    )


@pytest.fixture(scope="session")
def tenants(db: Databases) -> tuple[TenantData, TenantData]:
    with db.owner.begin() as conn:
        return build_tenant(conn, "alpha"), build_tenant(conn, "bravo")


@pytest.fixture
def alpha_owner(db: Databases, tenants: tuple[TenantData, TenantData]) -> Iterator[TestClient]:
    """An API client signed in as the alpha tenant's owner."""
    with TestClient(create_app()) as client:
        signed_in = service.sign_in_verified_email("owner@alpha.test", None, "/app", "pytest")
        client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        yield client
