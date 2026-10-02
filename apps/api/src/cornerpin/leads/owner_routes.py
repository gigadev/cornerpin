"""Inquiries and hold requests in the owner portal (P1-08). Approving a hold puts an available
lot on hold in the same transaction (ADR-028); the lots trigger records the change."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.tenancy import tenant_session
from cornerpin.leads.consent import allowed_channels_sql
from cornerpin.leads.schemas import HoldDecision, HoldRequestOut, InquiryOut

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["leads"])

Responses = dict[int | str, dict[str, Any]]

NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}
LIST_LIMIT = 200

# Buyer rows are also visible to the buyer who made them (ADR-021), so an owner who is also a
# buyer elsewhere would see their own rows; filtering on app_tenant_id() keeps lists to this
# tenant.
INQUIRIES = f"""
    SELECT i.id, i.lot_id, l.number AS lot_number, s.name AS subdivision_name, i.name, i.email,
           i.phone, i.message, i.user_id IS NOT NULL AS signed_in, i.created_at,
           {allowed_channels_sql("i")} AS contact
    FROM inquiries i
    JOIN lots l ON l.id = i.lot_id
    JOIN subdivisions s ON s.id = l.subdivision_id
    WHERE i.tenant_id = app_tenant_id()
    ORDER BY i.created_at DESC
    LIMIT :limit
"""  # noqa: S608 -- interpolates a fixed SQL fragment

HOLD_REQUESTS = f"""
    SELECT h.id, h.lot_id, l.number AS lot_number, l.status AS lot_status,
           s.name AS subdivision_name, h.name, h.email, h.phone, h.message, h.status,
           h.created_at, h.decided_at, {allowed_channels_sql("h")} AS contact
    FROM hold_requests h
    JOIN lots l ON l.id = h.lot_id
    JOIN subdivisions s ON s.id = l.subdivision_id
    WHERE h.tenant_id = app_tenant_id() AND (CAST(:id AS uuid) IS NULL OR h.id = :id)
    ORDER BY h.status = 'pending' DESC, h.created_at DESC
    LIMIT :limit
"""  # noqa: S608 -- interpolates a fixed SQL fragment


@router.get("/inquiries", responses=NOT_FOUND)
def list_inquiries(tenant_id: UUID, user: SignedInUser) -> list[InquiryOut]:
    """Newest first."""
    with tenant_session(user, tenant_id) as session:
        rows = session.execute(text(INQUIRIES), {"limit": LIST_LIMIT}).all()
    return [InquiryOut.model_validate(row, from_attributes=True) for row in rows]


def _hold_requests(session: Session, hold_id: UUID | None = None) -> list[HoldRequestOut]:
    rows = session.execute(text(HOLD_REQUESTS), {"id": hold_id, "limit": LIST_LIMIT}).all()
    return [HoldRequestOut.model_validate(row, from_attributes=True) for row in rows]


@router.get("/hold-requests", responses=NOT_FOUND)
def list_hold_requests(tenant_id: UUID, user: SignedInUser) -> list[HoldRequestOut]:
    """Pending first, then newest first."""
    with tenant_session(user, tenant_id) as session:
        return _hold_requests(session)


@router.post(
    "/hold-requests/{hold_id}/decision",
    responses={
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "Already decided, or the lot is sold"},
    },
)
def decide_hold_request(
    tenant_id: UUID, hold_id: UUID, body: HoldDecision, user: SignedInUser
) -> HoldRequestOut:
    with tenant_session(user, tenant_id) as session:
        row = session.execute(
            text(
                "SELECT h.status, h.lot_id, l.status AS lot_status FROM hold_requests h"
                " JOIN lots l ON l.id = h.lot_id"
                " WHERE h.id = :id AND h.tenant_id = app_tenant_id() FOR UPDATE OF h, l"
            ),
            {"id": hold_id},
        ).one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        if row.status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "This request was already decided")
        if body.decision == "approve":
            if row.lot_status == "sold":
                raise HTTPException(status.HTTP_409_CONFLICT, "This lot is already sold")
            session.execute(
                text("UPDATE lots SET status = 'on_hold' WHERE id = :id AND status = 'available'"),
                {"id": row.lot_id},
            )
        session.execute(
            text(
                "UPDATE hold_requests SET status = CAST(:status AS hold_request_status),"
                " decided_by = app_user_id(), decided_at = now() WHERE id = :id"
            ),
            {"id": hold_id, "status": "approved" if body.decision == "approve" else "declined"},
        )
        return _hold_requests(session, hold_id)[0]
