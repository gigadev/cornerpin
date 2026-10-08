"""Outbox handlers for decisioning (ADR-045). Importing this module registers them."""

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.outbox import handler
from cornerpin.decisioning.events import ScoreLead
from cornerpin.decisioning.features import lead_features
from cornerpin.decisioning.scoring import get_scorer

LATEST = text(
    "SELECT model_version, inputs FROM risk_scores"
    " WHERE lead_id = :lead_id AND hold_request_id IS NULL"
    " ORDER BY scored_at DESC, id DESC LIMIT 1"
)

INSERT = text(
    "INSERT INTO risk_scores (tenant_id, lead_id, model_version, score, inputs, reasons)"
    " VALUES (:tenant_id, :lead_id, :model_version, :score, CAST(:inputs AS jsonb),"
    " CAST(:reasons AS jsonb))"
)


@handler(ScoreLead)
def score_lead(event: ScoreLead, session: Session) -> None:
    """Score the lead, keeping a new row only when the inputs or the model changed, so a burst
    of events (an inquiry's lead, consent and question) leaves one score."""
    subject = lead_features(session, event.lead_id)
    if subject is None:
        return
    inputs = subject.features.model_dump(mode="json")
    result = get_scorer().score(subject.features)
    latest = session.execute(LATEST, {"lead_id": subject.lead_id}).one_or_none()
    if latest is not None and (latest.model_version, latest.inputs) == (
        result.model_version,
        inputs,
    ):
        return
    session.execute(
        INSERT,
        {
            "tenant_id": subject.tenant_id,
            "lead_id": subject.lead_id,
            "model_version": result.model_version,
            "score": result.score,
            "inputs": json.dumps(inputs),
            "reasons": json.dumps([r.model_dump() for r in result.reasons]),
        },
    )
