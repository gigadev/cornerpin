"""What a lead's score may look at (ADR-045): the lead's own history and the lot it asked about,
never anything about the person. Changing this list means changing the ADR and the test that
pins it (tests/test_decisioning.py)."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.financing.terms import payment_to_income

OpenStage = Literal["new", "contacted", "engaged", "holding"]
PriceBand = Literal["low", "mid", "high"]


class LeadFeatures(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: OpenStage
    touches: int
    """Messages sent to the buyer."""
    replies: int
    """Verified replies from the buyer."""
    hold_requests: int
    hold_approved: bool
    days_since_first_contact: int
    days_since_buyer_activity: int | None
    """Since the buyer's last verified inquiry, hold request or reply; None if there's none."""
    opted_out: bool
    """The buyer's latest answer on email is no."""
    lot_price_band: PriceBand | None
    """Where the lot's price sits among its subdivision's priced lots."""
    listing_type: Literal["land_only", "lot_and_home"] | None
    phase_release: Literal["upcoming", "released"] | None


@dataclass(frozen=True)
class ScoringSubject:
    tenant_id: UUID
    lead_id: UUID
    features: LeadFeatures


# Read in the worker's session. Only verified events count as the buyer's own (ADR-035).
HISTORY = text(
    """
    SELECT l.tenant_id, l.stage::text AS stage,
      extract(day FROM now() - l.created_at)::int AS days_since_first_contact,
      (SELECT count(*) FROM lead_events e WHERE e.lead_id = l.id
         AND e.kind::text = 'message_sent') AS touches,
      (SELECT count(*) FROM lead_events e WHERE e.lead_id = l.id
         AND e.kind::text = 'message_received' AND e.verified) AS replies,
      (SELECT count(*) FROM lead_events e WHERE e.lead_id = l.id
         AND e.kind::text = 'hold_requested') AS hold_requests,
      EXISTS (SELECT FROM lead_events e WHERE e.lead_id = l.id
         AND e.kind::text = 'hold_approved') AS hold_approved,
      (SELECT extract(day FROM now() - max(e.created_at))::int FROM lead_events e
         WHERE e.lead_id = l.id AND e.verified
           AND e.kind::text IN ('inquiry', 'hold_requested', 'message_received')
      ) AS days_since_buyer_activity,
      coalesce((SELECT NOT (e.detail->>'granted')::boolean FROM lead_events e
         WHERE e.lead_id = l.id AND e.kind::text = 'consent_changed'
           AND e.detail->>'channel' = 'email'
         ORDER BY e.created_at DESC LIMIT 1), false) AS opted_out,
      (SELECT e.lot_id FROM lead_events e WHERE e.lead_id = l.id AND e.lot_id IS NOT NULL
         ORDER BY e.created_at DESC LIMIT 1) AS lot_id
    FROM leads l WHERE l.id = :lead_id
    """
)

# The price's rank among the subdivision's priced lots, from 0 (cheapest) to 1.
LOT = text(
    """
    SELECT l.listing_type::text AS listing_type, p.release_status::text AS phase_release,
      CASE WHEN l.price IS NULL THEN NULL ELSE
        (SELECT count(*) FROM lots o WHERE o.subdivision_id = l.subdivision_id
           AND o.price < l.price)::float
        / nullif((SELECT count(*) FROM lots o WHERE o.subdivision_id = l.subdivision_id
           AND o.price IS NOT NULL) - 1, 0)
      END AS price_rank
    FROM lots l JOIN phases p ON p.id = l.phase_id WHERE l.id = :lot_id
    """
)


def price_band(rank: float | None) -> PriceBand | None:
    if rank is None:
        return None
    if rank < 1 / 3:
        return "low"
    return "high" if rank > 2 / 3 else "mid"


def lead_features(session: Session, lead_id: UUID) -> ScoringSubject | None:
    """The lead's features, or None if it's gone or closed (won and lost leads aren't scored)."""
    lead = session.execute(HISTORY, {"lead_id": lead_id}).one_or_none()
    if lead is None or lead.stage in ("won", "lost"):
        return None
    lot = (
        session.execute(LOT, {"lot_id": lead.lot_id}).one_or_none()
        if lead.lot_id is not None
        else None
    )
    features = LeadFeatures(
        stage=lead.stage,
        touches=lead.touches,
        replies=lead.replies,
        hold_requests=lead.hold_requests,
        hold_approved=lead.hold_approved,
        days_since_first_contact=lead.days_since_first_contact,
        days_since_buyer_activity=lead.days_since_buyer_activity,
        opted_out=lead.opted_out,
        lot_price_band=price_band(lot.price_rank) if lot else None,
        listing_type=lot.listing_type if lot else None,
        phase_release=lot.phase_release if lot else None,
    )
    return ScoringSubject(tenant_id=lead.tenant_id, lead_id=lead_id, features=features)


# --- financing applications (ADR-049), the demo tenant's synthetic module ---------------------


class ApplicationFeatures(BaseModel):
    """A financing application's terms and its lot. The buyer's stated income enters only as
    the share of it this loan's payment would take; nothing about who they are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    down_payment_ratio: float = Field(ge=0, le=1)
    term_months: int = Field(gt=0)
    payment_to_income: float = Field(ge=0)
    lot_price_band: PriceBand | None
    listing_type: Literal["land_only", "lot_and_home"] | None


@dataclass(frozen=True)
class ApplicationSubject:
    tenant_id: UUID
    application_id: UUID
    features: ApplicationFeatures


APPLICATION = text(
    """
    SELECT a.tenant_id, a.lot_id, a.amount, a.down_payment, a.term_months,
           a.income_band::text AS income_band, a.status::text AS status
    FROM financing_applications a WHERE a.id = :id
    """
)


def application_features(session: Session, application_id: UUID) -> ApplicationSubject | None:
    """The application's features, or None if it's gone or no longer waiting for a decision."""
    found = session.execute(APPLICATION, {"id": application_id}).one_or_none()
    if found is None or found.status != "submitted":
        return None
    lot = session.execute(LOT, {"lot_id": found.lot_id}).one_or_none()
    price = found.amount + found.down_payment
    features = ApplicationFeatures(
        down_payment_ratio=round(float(found.down_payment / price), 3),
        term_months=found.term_months,
        payment_to_income=payment_to_income(found.amount, found.term_months, found.income_band),
        lot_price_band=price_band(lot.price_rank) if lot else None,
        listing_type=lot.listing_type if lot else None,
    )
    return ApplicationSubject(
        tenant_id=found.tenant_id, application_id=application_id, features=features
    )
