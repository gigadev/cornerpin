"""The decisioning service's HTTP API (ADR-048). On Cloud Run only the API's service account may
invoke it (roles/run.invoker), so Cloud Run checks the caller's Google ID token before a request
arrives here. Locally it runs unauthenticated on its own port.

    uv run uvicorn cornerpin_decisioning.app:app --port 8200"""

from fastapi import FastAPI
from pydantic import BaseModel

from cornerpin_decisioning.contract import ApplicationScoreRequest, Score, ScoreRequest
from cornerpin_decisioning.model import current_application_scorer, current_scorer

app = FastAPI(title="Cornerpin decisioning", version="0.1.0")


class Health(BaseModel):
    status: str
    model_version: str
    application_model_version: str


@app.get("/health")
def health() -> Health:
    """Also loads the models, so a cold start pays for it here rather than on a score."""
    return Health(
        status="ok",
        model_version=current_scorer().version,
        application_model_version=current_application_scorer().version,
    )


@app.post("/v1/score")
def score(body: ScoreRequest) -> Score:
    """A lead's risk of falling through, with its reasons. Advice for a person (ADR-013)."""
    return current_scorer().score(body.features)


@app.post("/v1/score/application")
def score_application(body: ApplicationScoreRequest) -> Score:
    """A financing application's risk of falling behind, with its reasons (ADR-049). The demo
    tenant's synthetic module only; advice for a person, never a decision."""
    return current_application_scorer().score(body.features)
