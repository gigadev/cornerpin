"""Cloud Tasks and Cloud Scheduler (ADR-010, ADR-029). Dormant until the outbox runner is
"cloudtasks" and its settings exist; until then /internal/* is a 404.

After a commit that queued events, the dispatcher creates a Cloud Task that calls
/internal/outbox/drain on the API. Each drain then books a task for when the next waiting event
is due, such as a delayed follow-up or a retry (ADR-043). Cloud Scheduler calls the same
endpoint hourly, as a safety net, and /internal/housekeeping daily. Every call carries a
Google-signed OIDC token for the tasks service account, which is checked here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Protocol

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from cornerpin.core.auth.google import ISSUERS, JWKS_URL
from cornerpin.core.config import get_settings
from cornerpin.core.housekeeping import HousekeepingResult, run_housekeeping
from cornerpin.core.outbox import drain, schedule_next

TASKS_API = "https://cloudtasks.googleapis.com/v2"
DRAIN_PATH = "/internal/outbox/drain"

Post = Callable[[str, dict[str, Any]], None]


def _google_post() -> Post:
    """POST as the service's own Google identity (the Cloud Run service account)."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession

    credentials, _project = google.auth.default(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    session = AuthorizedSession(credentials)  # pyright: ignore[reportUnknownArgumentType]

    def post(url: str, body: dict[str, Any]) -> None:
        response = session.post(url, json=body, timeout=5)
        if response.status_code == 409:
            return  # a named task that already exists: the wake-up is booked
        response.raise_for_status()

    return post


@dataclass
class CloudTasksDispatcher:
    """Creates one HTTP task per notification. Concurrent drains are safe: the outbox query
    skips rows another drain has locked."""

    queue: str
    base_url: str
    service_account: str
    post: Post | None = None

    def notify(self) -> None:
        self._create({})

    def notify_at(self, when: datetime) -> None:
        """A task for a second or two after an event is due, which allows for clock skew. It is
        named after that second, so drains that ask for the same wake-up book it once."""
        at = max(when, datetime.now(UTC)).replace(microsecond=0) + timedelta(seconds=2)
        stamp = int(at.timestamp())
        self._create(
            {
                "name": f"{self.queue}/tasks/outbox-{stamp}",
                "scheduleTime": at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    def _create(self, extra: dict[str, Any]) -> None:
        if self.post is None:
            self.post = _google_post()
        self.post(
            f"{TASKS_API}/{self.queue}/tasks",
            {
                "task": {
                    **extra,
                    "httpRequest": {
                        "httpMethod": "POST",
                        "url": f"{self.base_url}{DRAIN_PATH}",
                        "oidcToken": {
                            "serviceAccountEmail": self.service_account,
                            "audience": self.base_url,
                        },
                    },
                }
            },
        )


def cloud_tasks_dispatcher() -> CloudTasksDispatcher | None:
    settings = get_settings()
    if not (
        settings.cloud_tasks_queue and settings.internal_base_url and settings.tasks_service_account
    ):
        return None
    return CloudTasksDispatcher(
        queue=settings.cloud_tasks_queue,
        base_url=settings.internal_base_url,
        service_account=settings.tasks_service_account,
    )


# --- the endpoints those tasks call --------------------------------------------------------


class TaskCallerVerifier(Protocol):
    def verify(self, token: str) -> bool: ...


class GoogleOidcVerifier:
    """Accepts a Google-signed ID token for one service account and audience."""

    def __init__(self, audience: str, service_account: str) -> None:
        self._audience = audience
        self._service_account = service_account
        self._jwks = jwt.PyJWKClient(JWKS_URL)

    def verify(self, token: str) -> bool:
        try:
            key = self._jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, key.key, algorithms=["RS256"], audience=self._audience, issuer=ISSUERS
            )
        except jwt.PyJWTError:
            return False
        return claims.get("email") == self._service_account and claims.get("email_verified") is True


@lru_cache
def get_task_verifier() -> TaskCallerVerifier | None:
    dispatcher = cloud_tasks_dispatcher()
    if get_settings().outbox_runner != "cloudtasks" or dispatcher is None:
        return None
    return GoogleOidcVerifier(dispatcher.base_url, dispatcher.service_account)


def require_task_caller(
    verifier: Annotated[TaskCallerVerifier | None, Depends(get_task_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if verifier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not verifier.verify(token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")


router = APIRouter(prefix="/internal", dependencies=[Depends(require_task_caller)])


class DrainResult(BaseModel):
    processed: int


@router.post("/outbox/drain")
def drain_outbox() -> DrainResult:
    processed = drain()
    schedule_next()
    return DrainResult(processed=processed)


@router.post("/housekeeping")
def housekeeping() -> HousekeepingResult:
    return run_housekeeping()
