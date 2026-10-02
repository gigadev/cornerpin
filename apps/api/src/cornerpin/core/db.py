"""Database sessions. Every API transaction runs as one of two roles (ADR-021):

- user_session: a signed-in user, optionally acting for a tenant they belong to.
- public_session: an anonymous visitor; sees published listings only.
- auth_session: sign-in and session lookup, before a user is known (ADR-023).
- worker_session: the outbox runner (ADR-023).

The login role holds no privileges of its own, so a connection used outside these helpers
cannot read anything. user_id and tenant_id must come from the verified session, never from
the request body.
"""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from cornerpin.core.config import get_settings


@lru_cache
def api_engine() -> Engine:
    return create_engine(get_settings().api_database_url, pool_pre_ping=True)


@contextmanager
def user_session(
    user_id: UUID, tenant_id: UUID | None = None, *, engine: Engine | None = None
) -> Generator[Session]:
    """One transaction as cornerpin_user. tenant_id only takes effect if the user is a member
    of that tenant; the database checks this, not the caller."""
    with Session(engine or api_engine()) as session, session.begin():
        session.execute(text("SET LOCAL ROLE cornerpin_user"))
        session.execute(
            text(
                "SELECT set_config('app.user_id', :user_id, true),"
                " set_config('app.tenant_id', :tenant_id, true)"
            ),
            {"user_id": str(user_id), "tenant_id": str(tenant_id) if tenant_id else ""},
        )
        yield session


@contextmanager
def _role_session(role: str, engine: Engine | None) -> Generator[Session]:
    with Session(engine or api_engine()) as session, session.begin():
        session.execute(text(f"SET LOCAL ROLE {role}"))
        yield session


@contextmanager
def public_session(*, engine: Engine | None = None) -> Generator[Session]:
    """One transaction as cornerpin_public: published listings, read-only."""
    with _role_session("cornerpin_public", engine) as session:
        yield session


@contextmanager
def auth_session(*, engine: Engine | None = None) -> Generator[Session]:
    """One transaction as cornerpin_auth. Only the auth module uses this."""
    with _role_session("cornerpin_auth", engine) as session:
        yield session


@contextmanager
def worker_session(*, engine: Engine | None = None) -> Generator[Session]:
    """One transaction as cornerpin_worker. Only the outbox runner uses this."""
    with _role_session("cornerpin_worker", engine) as session:
        yield session
