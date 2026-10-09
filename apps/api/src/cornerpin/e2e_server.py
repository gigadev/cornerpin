"""The API for Playwright: a fresh `cornerpin_e2e` database, the demo seed plus a second tenant,
and the in-process outbox runner sending to Mailpit. Started by apps/web/playwright.config.ts.

    uv run python -m cornerpin.e2e_server 8100
"""

import io
import os
import shutil
import sys
from uuid import NAMESPACE_URL, uuid4, uuid5

import uvicorn
from PIL import Image
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from cornerpin.core.config import REPO_ROOT, get_settings
from cornerpin.core.storage import LocalStorage
from cornerpin.devtools import recreate_database
from cornerpin.seed import DEMO_SLUG, DEMO_TENANT_ID, seed

E2E_DATABASE = "cornerpin_e2e"
# Uploads from Playwright runs, kept apart from the developer's var/storage and emptied each run.
E2E_STORAGE = REPO_ROOT / "var" / "e2e-storage"
PLAT_PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
# Keep in sync with apps/web/e2e/fixtures.ts.
OTHER_TENANT_ID = uuid5(NAMESPACE_URL, "https://cornerpin.app/tenants/e2e-other")
# Owners of the demo tenant: one per Playwright project for the sign-in tests, and one per
# project for the portal tests' saved session, so parallel tests never share an inbox.
OTHER_OWNERS = (
    "owner@other.cornerpin.test",
    "dashboard+mobile@other.cornerpin.test",
    "dashboard+desktop@other.cornerpin.test",
)
PROJECT_OWNERS = (
    "owner+mobile@demo.cornerpin.test",
    "owner+desktop@demo.cornerpin.test",
    "portal+mobile@demo.cornerpin.test",
    "portal+desktop@demo.cornerpin.test",
)


def seed_e2e(conn: Connection) -> None:
    seed(conn)
    conn.execute(
        text("INSERT INTO tenants (id, name) VALUES (:id, 'Other Land Co.')"),
        {"id": OTHER_TENANT_ID},
    )
    # Owners of the empty tenant: one for the cross-tenant checks, and one per Playwright project
    # for the dashboard's empty states (P3-07), each with an inbox of its own.
    for email in OTHER_OWNERS:
        other_owner = conn.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}
        ).scalar_one()
        conn.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
            {"t": OTHER_TENANT_ID, "u": other_owner},
        )
    # One owner per Playwright project, so parallel projects never read each other's email.
    for email in PROJECT_OWNERS:
        user_id = conn.execute(
            text("INSERT INTO users (email) VALUES (:e) RETURNING id"), {"e": email}
        ).scalar_one()
        conn.execute(
            text("INSERT INTO memberships (tenant_id, user_id, role) VALUES (:t, :u, 'owner')"),
            {"t": DEMO_TENANT_ID, "u": user_id},
        )


def seed_media(conn: Connection) -> None:
    """Photos and a plat for Juniper Bench lot 2-5 (published), and a photo for lot 2-13
    (phase 2, unpublished), so the public-page tests can check both sides. Keep in sync with
    DEMO_LOTS in apps/web/e2e/fixtures.ts."""
    storage = LocalStorage(E2E_STORAGE)
    lots = {
        number: lot_id
        for number, lot_id in conn.execute(
            text(
                "SELECT l.number, l.id FROM lots l JOIN subdivisions s ON s.id = l.subdivision_id"
                " WHERE s.slug = :slug AND l.number IN ('2-5', '2-13')"
            ),
            {"slug": DEMO_SLUG},
        )
    }
    photos = (
        ("2-5", "Front of the house", 0),
        ("2-5", "Back porch", 1),
        ("2-13", "Not yet public", 0),
    )
    for number, caption, order in photos:
        lot_id = lots[number]
        key = f"tenants/{DEMO_TENANT_ID}/lots/{lot_id}/photos/{uuid4()}.png"
        out = io.BytesIO()
        Image.new("RGB", (640, 480), (120, 150, 100)).save(out, "PNG")
        storage.put(key, out.getvalue(), "image/png")
        conn.execute(
            text(
                "INSERT INTO lot_media (tenant_id, lot_id, storage_key, content_type, caption,"
                " sort_order, width, height) VALUES (:t, :l, :k, 'image/png', :c, :o, 640, 480)"
            ),
            {"t": DEMO_TENANT_ID, "l": lot_id, "k": key, "c": caption, "o": order},
        )
    key = f"tenants/{DEMO_TENANT_ID}/lots/{lots['2-5']}/documents/{uuid4()}.pdf"
    storage.put(key, PLAT_PDF, "application/pdf")
    conn.execute(
        text(
            "INSERT INTO lot_documents (tenant_id, lot_id, kind, title, storage_key, content_type,"
            " size_bytes) VALUES (:t, :l, 'plat', 'Recorded plat', :k, 'application/pdf', :n)"
        ),
        {"t": DEMO_TENANT_ID, "l": lots["2-5"], "k": key, "n": len(PLAT_PDF)},
    )


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    dev = get_settings()
    owner_url = make_url(dev.database_url).set(database=E2E_DATABASE)
    api_url = make_url(dev.api_database_url).set(database=E2E_DATABASE)

    shutil.rmtree(E2E_STORAGE, ignore_errors=True)
    recreate_database(owner_url)
    engine = create_engine(owner_url)
    with engine.begin() as conn:
        seed_e2e(conn)
        seed_media(conn)
    engine.dispose()

    os.environ["DATABASE_URL"] = owner_url.render_as_string(hide_password=False)
    os.environ["API_DATABASE_URL"] = api_url.render_as_string(hide_password=False)
    os.environ.setdefault("WEB_ORIGIN", "http://localhost:3310")
    os.environ["STORAGE_DIR"] = str(E2E_STORAGE)
    os.environ["OUTBOX_RUNNER"] = "inprocess"
    os.environ["MAGIC_LINKS_PER_15_MINUTES"] = "1000"
    get_settings.cache_clear()

    uvicorn.run("cornerpin.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
