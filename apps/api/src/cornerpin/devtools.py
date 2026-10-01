"""Throwaway databases for tests and end-to-end runs. Local and CI only."""

from sqlalchemy import URL, create_engine, text

from cornerpin.core.config import REPO_ROOT


def recreate_database(owner_url: URL) -> None:
    """Drop and create the database named in owner_url, then migrate it to head."""
    from alembic import command
    from alembic.config import Config

    name = owner_url.database
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"refusing to recreate database {name!r}")
    admin = create_engine(owner_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {name}"))
    finally:
        admin.dispose()

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", owner_url.render_as_string(hide_password=False))
    command.upgrade(config, "head")
