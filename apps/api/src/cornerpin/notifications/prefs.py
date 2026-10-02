"""What a user wants to hear about (P1-08), and the lookups the handlers use (P1-09). Until a
user changes anything they get the table's defaults."""

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.db import user_session

router = APIRouter(tags=["notifications"])


class NotificationPrefs(BaseModel):
    email_saved_lot_changes: bool = True
    push_saved_lot_changes: bool = False


def prefs_of(session: Session, user_id: UUID) -> NotificationPrefs:
    row = session.execute(
        text(
            "SELECT email_saved_lot_changes, push_saved_lot_changes FROM notification_prefs"
            " WHERE user_id = :u"
        ),
        {"u": user_id},
    ).one_or_none()
    return (
        NotificationPrefs()
        if row is None
        else NotificationPrefs.model_validate(row, from_attributes=True)
    )


@router.get("/me/notification-prefs")
def get_prefs(user: SignedInUser) -> NotificationPrefs:
    with user_session(user.id) as session:
        return prefs_of(session, user.id)


@router.put("/me/notification-prefs")
def put_prefs(body: NotificationPrefs, user: SignedInUser) -> NotificationPrefs:
    with user_session(user.id) as session:
        session.execute(
            text(
                "INSERT INTO notification_prefs (user_id, email_saved_lot_changes,"
                " push_saved_lot_changes) VALUES (:u, :email, :push)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                " email_saved_lot_changes = EXCLUDED.email_saved_lot_changes,"
                " push_saved_lot_changes = EXCLUDED.push_saved_lot_changes"
            ),
            {
                "u": user.id,
                "email": body.email_saved_lot_changes,
                "push": body.push_saved_lot_changes,
            },
        )
    return body
