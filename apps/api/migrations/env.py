from alembic import context
from sqlalchemy import create_engine, pool

from cornerpin.core.config import get_settings

config = context.config

# Models register their metadata here from P1-02 on; until then migrations are hand-written.
target_metadata = None


def database_url() -> str:
    # Tests point Alembic at their own database through sqlalchemy.url.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
