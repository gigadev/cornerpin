"""The signed-in user and the tenants they belong to. The owner portal asks for a tenant here
first; a tenant the user is not a member of is a 404 (P1-03). Buyers keep their name, phone and
time zone here (P1-08); the email address is the one they signed in with and never changes."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.db import user_session
from cornerpin.core.fields import Phone, TimeZone
from cornerpin.core.tenancy import constraint_errors

router = APIRouter(tags=["accounts"])

Role = Literal["owner", "staff"]


class Membership(BaseModel):
    tenant_id: UUID
    tenant_name: str
    role: Role


class Me(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    phone: str | None
    time_zone: str | None
    memberships: list[Membership]


DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class MeUpdate(BaseModel):
    """Only the fields sent are changed; an empty name or null clears it."""

    display_name: DisplayName | None = None
    phone: Phone | None = None
    time_zone: TimeZone | None = None


class Tenant(BaseModel):
    id: UUID
    name: str
    role: Role


@router.get("/me")
def me(user: SignedInUser) -> Me:
    with user_session(user.id) as session:
        return _me(session, user.id)


@router.patch("/me")
def update_me(body: MeUpdate, user: SignedInUser) -> Me:
    changes = body.model_dump(include=body.model_fields_set)
    if "display_name" in changes:
        changes["display_name"] = changes["display_name"] or None
    with user_session(user.id) as session:
        if changes:
            assignments = ", ".join(f"{column} = :{column}" for column in changes)
            with constraint_errors({}):
                session.execute(
                    text(f"UPDATE users SET {assignments} WHERE id = :id"),  # noqa: S608 -- MeUpdate's own field names
                    {**changes, "id": user.id},
                )
        return _me(session, user.id)


def _me(session: Session, user_id: UUID) -> Me:
    row = session.execute(
        text("SELECT id, email, display_name, phone, time_zone FROM users WHERE id = :id"),
        {"id": user_id},
    ).one()
    memberships = session.execute(
        text(
            "SELECT m.tenant_id, t.name AS tenant_name, m.role FROM memberships m"
            " JOIN tenants t ON t.id = m.tenant_id ORDER BY t.name"
        )
    ).all()
    return Me(
        id=row.id,
        email=row.email,
        display_name=row.display_name,
        phone=row.phone,
        time_zone=row.time_zone,
        memberships=[Membership.model_validate(m, from_attributes=True) for m in memberships],
    )


@router.get(
    "/tenants/{tenant_id}",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Not a member of this tenant"}},
)
def tenant(tenant_id: UUID, user: SignedInUser) -> Tenant:
    with user_session(user.id, tenant_id) as session:
        row = session.execute(
            text(
                "SELECT t.id, t.name, m.role FROM tenants t"
                " JOIN memberships m ON m.tenant_id = t.id"
                " WHERE t.id = app_tenant_id()"
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return Tenant(id=row.id, name=row.name, role=row.role)
