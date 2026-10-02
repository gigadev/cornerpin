"""Who people are, for messages sent in the background. Runs in the worker's session."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def member_ids(session: Session, tenant_id: UUID) -> list[UUID]:
    """Owners and staff of the tenant."""
    return list(
        session.execute(
            text("SELECT user_id FROM memberships WHERE tenant_id = :t ORDER BY created_at"),
            {"t": tenant_id},
        ).scalars()
    )


def email_of(session: Session, user_id: UUID) -> str | None:
    email: str | None = session.execute(
        text("SELECT email FROM users WHERE id = :id"), {"id": user_id}
    ).scalar_one_or_none()
    return email
