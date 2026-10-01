"""The API for Playwright: a fresh `cornerpin_e2e` database, the demo seed plus a second tenant,
and the in-process outbox runner sending to Mailpit. Started by apps/web/playwright.config.ts.

    uv run python -m cornerpin.e2e_server 8100
"""

import os
import shutil
import sys
from uuid import NAMESPACE_URL, uuid5

import uvicorn
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url

from cornerpin.core.config import REPO_ROOT, get_settings
from cornerpin.devtools import recreate_database
from cornerpin.seed import DEMO_TENANT_ID, seed

E2E_DATABASE = "cornerpin_e2e"
# Uploads from Playwright runs, kept apart from the developer's var/storage and emptied each run.
E2E_STORAGE = REPO_ROOT / "var" / "e2e-storage"
# Keep in sync with apps/web/e2e/fixtures.ts.
OTHER_TENANT_ID = uuid5(NAMESPACE_URL, "https://cornerpin.app/tenants/e2e-other")
# Owners of the demo tenant: one per Playwright project for the sign-in tests, and one per
# project for the portal tests' saved session, so parallel tests never share an inbox.
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
    other_owner = conn.execute(
        text("INSERT INTO users (email) VALUES ('owner@other.cornerpin.test') RETURNING id")
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


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    dev = get_settings()
    owner_url = make_url(dev.database_url).set(database=E2E_DATABASE)
    api_url = make_url(dev.api_database_url).set(database=E2E_DATABASE)

    recreate_database(owner_url)
    engine = create_engine(owner_url)
    with engine.begin() as conn:
        seed_e2e(conn)
    engine.dispose()

    os.environ["DATABASE_URL"] = owner_url.render_as_string(hide_password=False)
    os.environ["API_DATABASE_URL"] = api_url.render_as_string(hide_password=False)
    os.environ.setdefault("WEB_ORIGIN", "http://localhost:3100")
    shutil.rmtree(E2E_STORAGE, ignore_errors=True)
    os.environ["STORAGE_DIR"] = str(E2E_STORAGE)
    os.environ["OUTBOX_RUNNER"] = "inprocess"
    os.environ["MAGIC_LINKS_PER_15_MINUTES"] = "1000"
    get_settings.cache_clear()

    uvicorn.run("cornerpin.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
