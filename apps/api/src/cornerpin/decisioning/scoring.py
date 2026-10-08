"""Scorers (ADR-013, ADR-045, ADR-048). A score is a lead's risk of falling through, from 0 to 1,
with the reasons behind it. Every scorer takes the same features and returns the same shape.

The trained model lives in the decisioning service (apps/decisioning), never in the API image:
the API sends features to it over HTTP, with a Google ID token on Cloud Run. Locally, with no
DECISIONING_URL, the service's code runs in-process from the dev environment instead."""

from collections.abc import Callable
from functools import cache
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from cornerpin.core.config import get_settings
from cornerpin.decisioning.features import LeadFeatures

# Seconds. A cold start (the service waking from zero and loading the model) measured 10.6 s on
# Cloud Run; a slower one still gets a retry from the outbox.
SERVICE_TIMEOUT = 30.0


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


TokenSource = Callable[[str], str]


def google_id_token(audience: str) -> str:
    """An ID token for the service, from Cloud Run's metadata server (the API's identity)."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    token: object = id_token.fetch_id_token(Request(), audience)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(token, str):
        raise RuntimeError("no ID token from the metadata server")
    return token


class ServiceScorer:
    """Scores through the decisioning service. A failure raises, so the outbox retries the
    event and nothing is stored until a score comes back (ADR-048)."""

    def __init__(
        self, url: str, *, token: TokenSource | None = None, client: httpx.Client | None = None
    ) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._client = client or httpx.Client(timeout=SERVICE_TIMEOUT)

    def score(self, features: LeadFeatures) -> Score:
        headers = {"Authorization": f"Bearer {self._token(self._url)}"} if self._token else {}
        response = self._client.post(
            f"{self._url}/v1/score",
            json={"features": features.model_dump(mode="json")},
            headers=headers,
        )
        response.raise_for_status()
        return Score.model_validate(response.json())


class InProcessScorer:
    """The service's model, run in this process. Local development and tests only: the API's
    own dependencies don't include it, and the API refuses to start outside local without
    DECISIONING_URL."""

    def score(self, features: LeadFeatures) -> Score:
        from cornerpin_decisioning.contract import Features
        from cornerpin_decisioning.model import current_scorer

        result = current_scorer().score(Features.model_validate(features.model_dump()))
        return Score.model_validate(result.model_dump())


@cache
def get_scorer() -> Scorer:
    """The service when DECISIONING_URL is set (with an ID token for an https URL), else
    in-process. The rules baseline stays as the documented reference (ADR-046)."""
    url = get_settings().decisioning_url
    if url:
        return ServiceScorer(url, token=google_id_token if url.startswith("https://") else None)
    return InProcessScorer()
