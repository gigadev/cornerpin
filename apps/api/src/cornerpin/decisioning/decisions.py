"""Scores as owners see them, and what they decided having seen one (ADR-013, ADR-045,
ADR-047). Other modules show scores and record decisions through this module, never by
touching its tables."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

DecisionKind = Literal["hold_approved", "hold_declined", "lead_won", "lead_lost"]


class ScoreReason(BaseModel):
    code: str
    text: str
    weight: float = Field(description="How much it moved the risk: positive raised it")


class LeadScore(BaseModel):
    """A lead's risk of falling through, from 0 to 1. Advice for a person, never a decision."""

    id: UUID
    score: float
    model_version: str
    reasons: list[ScoreReason] = Field(description="Biggest effect first")
    scored_at: datetime


def _score_json(alias: str) -> str:
    return (
        f"jsonb_build_object('id', {alias}.id, 'score', {alias}.score,"
        f" 'model_version', {alias}.model_version, 'reasons', {alias}.reasons,"
        f" 'scored_at', {alias}.scored_at)"
    )


def latest_score_sql(lead_id: str) -> str:
    """A SQL expression: the lead's latest score as JSON, or NULL. `lead_id` is a column."""
    return (
        f"(SELECT {_score_json('r')} FROM risk_scores r"  # noqa: S608 -- fixed SQL
        f" WHERE r.lead_id = {lead_id} AND r.hold_request_id IS NULL"
        " ORDER BY r.scored_at DESC, r.id DESC LIMIT 1)"
    )


def latest_application_score_sql(application_id: str) -> str:
    """A SQL expression: a financing application's latest score as JSON, or NULL (ADR-049)."""
    return (
        f"(SELECT {_score_json('r')} FROM risk_scores r"  # noqa: S608 -- fixed SQL
        f" WHERE r.financing_application_id = {application_id}"
        " ORDER BY r.scored_at DESC, r.id DESC LIMIT 1)"
    )


class UnknownScore(Exception):
    """The score named isn't one of this lead's."""


def record(
    session: Session,
    *,
    lead_id: UUID,
    kind: DecisionKind,
    score_id: UUID | None,
    hold_request_id: UUID | None = None,
) -> None:
    """Log a decision as the signed-in owner or staff member, with the score they saw (None
    if none was shown). Runs in their tenant session."""
    if score_id is not None:
        known = session.execute(
            text("SELECT EXISTS (SELECT FROM risk_scores WHERE id = :s AND lead_id = :l)"),
            {"s": score_id, "l": lead_id},
        ).scalar_one()
        if not known:
            raise UnknownScore(str(score_id))
    session.execute(
        text(
            "INSERT INTO decisions (tenant_id, lead_id, hold_request_id, kind, decided_by,"
            " decided_by_email, risk_score_id)"
            " SELECT app_tenant_id(), :lead, :hold, CAST(:kind AS decision_kind), u.id, u.email,"
            " :score FROM users u WHERE u.id = app_user_id()"
        ),
        {"lead": lead_id, "hold": hold_request_id, "kind": kind, "score": score_id},
    )


class Decision(BaseModel):
    id: UUID
    kind: DecisionKind
    decided_at: datetime
    decided_by_email: str
    score: LeadScore | None
    lot_id: UUID | None
    lot_number: str | None
    subdivision_name: str | None


DECISIONS = f"""
    SELECT d.id, d.kind::text AS kind, d.decided_at, d.decided_by_email,
           CASE WHEN r.id IS NULL THEN NULL ELSE {_score_json("r")} END AS score,
           lot.id AS lot_id, lot.number AS lot_number, s.name AS subdivision_name
    FROM decisions d
    LEFT JOIN risk_scores r ON r.id = d.risk_score_id
    LEFT JOIN hold_requests h ON h.id = d.hold_request_id
    LEFT JOIN lots lot ON lot.id = h.lot_id
    LEFT JOIN subdivisions s ON s.id = lot.subdivision_id
    WHERE d.lead_id = :lead AND d.tenant_id = app_tenant_id()
    ORDER BY d.decided_at DESC, d.id
"""  # noqa: S608 -- interpolates a fixed SQL fragment


def decisions_of(session: Session, lead_id: UUID) -> list[Decision]:
    rows = session.execute(text(DECISIONS), {"lead": lead_id}).all()
    return [Decision.model_validate(row, from_attributes=True) for row in rows]
