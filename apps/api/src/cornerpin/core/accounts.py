"""The signed-in user and the tenants they belong to. The owner portal asks for a tenant here
first; a tenant the user is not a member of is a 404 (P1-03)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.db import user_session

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
    memberships: list[Membership]


class Tenant(BaseModel):
    id: UUID
    name: str
    role: Role


@router.get("/me")
def me(user: SignedInUser) -> Me:
    with user_session(user.id) as session:
        row = session.execute(
            text("SELECT id, email, display_name FROM users WHERE id = :id"), {"id": user.id}
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
