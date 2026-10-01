"""Tenant-scoped transactions for the owner portal, and turning constraint violations into HTTP
errors."""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import CurrentUser
from cornerpin.core.db import user_session

UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"


@contextmanager
def tenant_session(user: CurrentUser, tenant_id: UUID) -> Generator[Session]:
    """One transaction acting for `tenant_id`. 404 unless the user is a member: the database
    decides membership (ADR-021), and a non-member sees the same answer as a missing tenant."""
    with user_session(user.id, tenant_id) as session:
        if session.execute(text("SELECT app_tenant_id()")).scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        yield session


@contextmanager
def constraint_errors(
    messages: Mapping[str, str],
    *,
    foreign_key_status: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
) -> Generator[None]:
    """Map database constraint violations to HTTP errors: duplicates are 409, failed checks 422,
    and foreign keys `foreign_key_status` (409 when deleting something still referenced).
    `messages` gives a human message per constraint name."""
    try:
        yield
    except IntegrityError as exc:
        orig = exc.orig
        sqlstate = getattr(orig, "sqlstate", None)
        diag = getattr(orig, "diag", None)
        constraint = getattr(diag, "constraint_name", None) or ""
        detail = messages.get(constraint, "That change conflicts with existing data")
        if sqlstate == UNIQUE_VIOLATION:
            raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc
        if sqlstate == FOREIGN_KEY_VIOLATION:
            raise HTTPException(foreign_key_status, detail) from exc
        if sqlstate == CHECK_VIOLATION:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail) from exc
        raise
