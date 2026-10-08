"""Scorers (ADR-013, ADR-045). A score is a lead's risk of falling through, from 0 to 1, with
the reasons behind it. Every scorer takes the same features and returns the same shape, so the
rules baseline, the trained model (P3-02) and the decisioning service (P3-04) are
interchangeable."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from cornerpin.decisioning.features import LeadFeatures


class Reason(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    text: str
    weight: float
    """How much it moved the risk: positive raises it, negative lowers it."""


class Score(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_version: str
    score: float
    reasons: list[Reason]


class Scorer(Protocol):
    def score(self, features: LeadFeatures) -> Score: ...


QUIET_DAYS = 30
NO_REPLY_TOUCHES = 2


class RulesBaseline:
    """Hand-set weights in plain words: the first scorer (P3-01), kept as the reference the
    trained model is compared with (ADR-046)."""

    version = "rules-v1"
    base = 0.5

    def score(self, features: LeadFeatures) -> Score:
        f = features
        found: list[Reason] = []

        def reason(code: str, text: str, weight: float) -> None:
            found.append(Reason(code=code, text=text, weight=weight))

        if f.opted_out:
            reason("opted_out", "Asked not to be emailed", 0.25)
        if f.replies:
            reason("replied", _count(f.replies, "Replied to a message", "Replied {n} times"), -0.15)
        elif f.touches >= NO_REPLY_TOUCHES:
            reason("no_reply", f"No reply to {f.touches} messages", 0.2)
        if f.hold_approved:
            reason("hold_approved", "Has an approved hold", -0.15)
        elif f.hold_requests:
            reason("asked_for_hold", "Asked to hold a lot", -0.15)
        if f.days_since_buyer_activity is not None:
            if f.days_since_buyer_activity > QUIET_DAYS:
                reason("quiet", f"Quiet for {f.days_since_buyer_activity} days", 0.15)
            elif f.days_since_buyer_activity <= 7:
                reason("recent", "Active in the last week", -0.05)
        if f.phase_release == "upcoming":
            reason("phase_upcoming", "The lot's phase isn't released yet", 0.05)
        if not found:
            reason("little_history", "Not much history yet", 0.0)

        total = self.base + sum(r.weight for r in found)
        return Score(
            model_version=self.version,
            score=round(min(max(total, 0.02), 0.98), 3),
            reasons=sorted(found, key=lambda r: abs(r.weight), reverse=True),
        )


def _count(n: int, one: str, many: str) -> str:
    return one if n == 1 else many.format(n=n)


def get_scorer() -> Scorer:
    """The trained model (ADR-046). The rules baseline stays as the documented reference."""
    from cornerpin.decisioning.model import current_scorer

    return current_scorer()
