"""Leads in the owner portal (P2-02, ADR-035): the list by stage, a lead's timeline, stage
changes, notes, and marking a handoff handled. Leads and their events are written by triggers
from buyer activity; owners change only the stage and the handoff, and add notes."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.tenancy import tenant_session
from cornerpin.leads.consent import allowed_channels_sql
from cornerpin.leads.schemas import (
    LeadDetail,
    LeadEvent,
    LeadList,
    LeadLot,
    LeadStage,
    LeadSummary,
    LeadUpdate,
    NoteCreate,
    StageCount,
)

router = APIRouter(prefix="/tenants/{tenant_id}/leads", tags=["leads"])

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}
LIST_LIMIT = 200
STAGES: tuple[LeadStage, ...] = ("new", "contacted", "engaged", "holding", "won", "lost")
# The buyer's own actions; everything else is the owner's or the system's.
BUYER_KINDS = (
    "inquiry",
    "hold_requested",
    "hold_withdrawn",
    "consent_changed",
    "message_received",
)

# An owner who is also a buyer elsewhere sees only this tenant's leads: buyers never see leads,
# and app_tenant_id() narrows it to the tenant in the URL.
LEADS = f"""
    SELECT l.id, l.name, l.email, l.phone, l.stage::text AS stage, l.source,
           l.user_id IS NOT NULL AS signed_in, {allowed_channels_sql("l")} AS contact,
           coalesce((
             SELECT jsonb_agg(jsonb_build_object('lot_id', lot.id, 'number', lot.number,
                                                 'subdivision_name', s.name)
                              ORDER BY s.name, lot.number COLLATE lot_number)
             FROM (SELECT DISTINCT e.lot_id FROM lead_events e
                   WHERE e.lead_id = l.id AND e.lot_id IS NOT NULL) seen
             JOIN lots lot ON lot.id = seen.lot_id
             JOIN subdivisions s ON s.id = lot.subdivision_id
           ), '[]'::jsonb) AS lots,
           l.handoff_at, l.handoff_reason, l.last_activity_at, l.created_at
    FROM leads l
    WHERE l.tenant_id = app_tenant_id()
      AND (CAST(:id AS uuid) IS NULL OR l.id = :id)
      AND (CAST(:stage AS lead_stage) IS NULL OR l.stage = CAST(:stage AS lead_stage))
      AND (NOT :needs_human OR l.handoff_at IS NOT NULL)
    ORDER BY l.last_activity_at DESC
    LIMIT :limit
"""  # noqa: S608 -- interpolates a fixed SQL fragment

COUNTS = """
    SELECT stage::text AS stage, count(*) AS total,
           count(*) FILTER (WHERE handoff_at IS NOT NULL) AS waiting
    FROM leads WHERE tenant_id = app_tenant_id() GROUP BY stage
"""

EVENTS = """
    SELECT e.id, e.kind::text AS kind, e.created_at, e.verified, e.actor_email, e.detail,
           lot.id AS lot_id, lot.number AS lot_number, s.name AS subdivision_name
    FROM lead_events e
    LEFT JOIN lots lot ON lot.id = e.lot_id
    LEFT JOIN subdivisions s ON s.id = lot.subdivision_id
    WHERE e.lead_id = :id AND e.tenant_id = app_tenant_id()
    ORDER BY e.created_at DESC, e.id
"""


def _summaries(
    session: Session,
    *,
    lead_id: UUID | None = None,
    stage: LeadStage | None = None,
    needs_human: bool = False,
) -> list[LeadSummary]:
    rows = session.execute(
        text(LEADS),
        {"id": lead_id, "stage": stage, "needs_human": needs_human, "limit": LIST_LIMIT},
    ).all()
    return [LeadSummary.model_validate(row, from_attributes=True) for row in rows]


def _event(row: Row[Any]) -> LeadEvent:
    detail: dict[str, Any] = row.detail
    lot = (
        LeadLot(lot_id=row.lot_id, number=row.lot_number, subdivision_name=row.subdivision_name)
        if row.lot_id is not None
        else None
    )
    return LeadEvent(
        id=row.id,
        kind=row.kind,
        created_at=row.created_at,
        by_buyer=row.kind in BUYER_KINDS,
        verified=row.verified,
        actor_email=row.actor_email,
        lot=lot,
        message=detail.get("message"),
        note=detail.get("text"),
        channel=detail.get("channel"),
        granted=detail.get("granted"),
        consent_source=detail.get("source") if row.kind == "consent_changed" else None,
        from_stage=detail.get("from"),
        to_stage=detail.get("to"),
        reason=detail.get("reason") or None,
        subject=detail.get("subject"),
    )


def _detail(session: Session, lead_id: UUID) -> LeadDetail:
    found = _summaries(session, lead_id=lead_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    events = [_event(row) for row in session.execute(text(EVENTS), {"id": lead_id})]
    return LeadDetail(**found[0].model_dump(), events=events)


@router.get("", responses=NOT_FOUND)
def list_leads(
    tenant_id: UUID,
    user: SignedInUser,
    stage: LeadStage | None = None,
    needs_human: bool = False,
) -> LeadList:
    """Newest activity first, optionally one stage or only those waiting for a person."""
    with tenant_session(user, tenant_id) as session:
        leads = _summaries(session, stage=stage, needs_human=needs_human)
        counted = {row.stage: row for row in session.execute(text(COUNTS))}
    return LeadList(
        leads=leads,
        stages=[StageCount(stage=s, count=counted[s].total if s in counted else 0) for s in STAGES],
        needs_human=sum(row.waiting for row in counted.values()),
    )


@router.get("/{lead_id}", responses=NOT_FOUND)
def get_lead(tenant_id: UUID, lead_id: UUID, user: SignedInUser) -> LeadDetail:
    with tenant_session(user, tenant_id) as session:
        return _detail(session, lead_id)


@router.patch("/{lead_id}", responses=NOT_FOUND)
def update_lead(tenant_id: UUID, lead_id: UUID, body: LeadUpdate, user: SignedInUser) -> LeadDetail:
    """Change the stage. The change goes on the timeline with who made it."""
    with tenant_session(user, tenant_id) as session:
        changed = session.execute(
            text(
                "UPDATE leads SET stage = CAST(:stage AS lead_stage)"
                " WHERE id = :id AND tenant_id = app_tenant_id() RETURNING id"
            ),
            {"id": lead_id, "stage": body.stage},
        ).first()
        if changed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        return _detail(session, lead_id)


@router.post("/{lead_id}/notes", status_code=status.HTTP_201_CREATED, responses=NOT_FOUND)
def add_note(tenant_id: UUID, lead_id: UUID, body: NoteCreate, user: SignedInUser) -> LeadDetail:
    with tenant_session(user, tenant_id) as session:
        _detail(session, lead_id)  # 404 unless it's this tenant's lead
        session.execute(
            text(
                "INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id, detail)"
                " VALUES (app_tenant_id(), :id, 'note', app_user_id(),"
                " jsonb_build_object('text', CAST(:text AS text)))"
            ),
            {"id": lead_id, "text": body.text},
        )
        return _detail(session, lead_id)


@router.post(
    "/{lead_id}/handoff/resolve",
    responses={**NOT_FOUND, status.HTTP_409_CONFLICT: {"description": "Not waiting for a person"}},
)
def resolve_handoff(tenant_id: UUID, lead_id: UUID, user: SignedInUser) -> LeadDetail:
    """Mark a handoff handled; it leaves the "needs a human" inbox."""
    with tenant_session(user, tenant_id) as session:
        lead = _detail(session, lead_id)
        if lead.handoff_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "This lead isn't waiting for anyone")
        session.execute(
            text("UPDATE leads SET handoff_at = NULL, handoff_reason = NULL WHERE id = :id"),
            {"id": lead_id},
        )
        return _detail(session, lead_id)
