"""What the decisioning service accepts and returns (ADR-048). The API keeps its own copy of
these shapes (cornerpin.decisioning.features and .scoring) so it never imports this package;
a test in the API's suite checks the two agree field for field."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OpenStage = Literal["new", "contacted", "engaged", "holding"]
PriceBand = Literal["low", "mid", "high"]


class Features(BaseModel):
    """A lead's history and the lot it asked about; never anything about the person
    (ADR-045)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: OpenStage
    touches: int
    replies: int
    hold_requests: int
    hold_approved: bool
    days_since_first_contact: int
    days_since_buyer_activity: int | None
    opted_out: bool
    lot_price_band: PriceBand | None
    listing_type: Literal["land_only", "lot_and_home"] | None
    phase_release: Literal["upcoming", "released"] | None


class ApplicationFeatures(BaseModel):
    """A financing application's terms and the lot it's for (ADR-049, demo tenant only). The
    buyer's stated income enters only as the share of it this loan's payment would take;
    nothing about who they are."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    down_payment_ratio: float = Field(ge=0, le=1)
    term_months: int = Field(gt=0)
    payment_to_income: float = Field(ge=0)
    lot_price_band: PriceBand | None
    listing_type: Literal["land_only", "lot_and_home"] | None


class Reason(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    text: str
    weight: float = Field(description="How much it moved the risk: positive raises it")


class Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_version: str
    score: float = Field(description="Risk of falling through, from 0 to 1")
    reasons: list[Reason] = Field(description="Biggest effect first")


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: Features


class ApplicationScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    features: ApplicationFeatures
