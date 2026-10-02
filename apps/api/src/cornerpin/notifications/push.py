"""Web push (ADR-005, ADR-029): saved-lot alerts for people who turn them on for a device.
Email stays the main channel. Dormant until VAPID keys are configured; only outbox handlers
send.

The worker POSTs to each subscription's endpoint, so endpoints are limited to the browsers'
push services: a made-up endpoint can't point the worker at anything else."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol
from urllib.parse import urlsplit

from fastapi import APIRouter, Query, Response, status
from pydantic import AfterValidator, BaseModel, Field
from pywebpush import (  # pyright: ignore[reportMissingTypeStubs]
    WebPushException,
    webpush,  # pyright: ignore[reportUnknownVariableType]
)
from sqlalchemy import text

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.config import get_settings
from cornerpin.core.db import user_session

# Chrome/Edge (FCM), Firefox, Safari and the old Edge push service.
PUSH_SERVICE_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com")
PUSH_SERVICE_SUFFIXES = (".push.apple.com", ".notify.windows.com")
TTL_SECONDS = 86_400


def _push_endpoint(value: str) -> str:
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    known = host in PUSH_SERVICE_HOSTS or host.endswith(PUSH_SERVICE_SUFFIXES)
    if parts.scheme != "https" or not known or parts.port not in (None, 443):
        raise ValueError("Not a browser push service endpoint")
    return value


PushEndpoint = Annotated[str, Field(max_length=2048), AfterValidator(_push_endpoint)]
Base64Key = Annotated[str, Field(min_length=8, max_length=256, pattern=r"^[A-Za-z0-9_=-]+$")]


@dataclass(frozen=True)
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


class PushGone(Exception):
    """The push service no longer knows this subscription; it should be removed."""


class PushSender(Protocol):
    def send(self, target: PushTarget, message: Mapping[str, str]) -> None:
        """Deliver `message` (title, body, url). Raises PushGone for a dead subscription."""
        ...


@dataclass(frozen=True)
class WebPushSender:
    private_key: str
    subject: str

    def send(self, target: PushTarget, message: Mapping[str, str]) -> None:
        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(dict(message)),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject},
                ttl=TTL_SECONDS,
                timeout=10,
            )
        except WebPushException as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) in (404, 410):
                raise PushGone(str(exc)) from exc
            raise


@lru_cache
def get_push_sender() -> PushSender | None:
    settings = get_settings()
    if not (settings.vapid_public_key and settings.vapid_private_key):
        return None
    return WebPushSender(private_key=settings.vapid_private_key, subject=settings.vapid_subject)


# --- subscriptions -------------------------------------------------------------------------

router = APIRouter(tags=["notifications"])


class PushConfig(BaseModel):
    public_key: str | None = Field(description="VAPID public key; null while push is off")


class SubscriptionKeys(BaseModel):
    p256dh: Base64Key
    auth: Base64Key


class PushSubscriptionIn(BaseModel):
    """The browser's PushSubscription, as `subscription.toJSON()` gives it."""

    endpoint: PushEndpoint
    keys: SubscriptionKeys


@router.get("/push/config")
def push_config() -> PushConfig:
    settings = get_settings()
    return PushConfig(public_key=settings.vapid_public_key if settings.push_enabled else None)


@router.put("/me/push-subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def add_subscription(body: PushSubscriptionIn, user: SignedInUser) -> Response:
    """Register this device. An endpoint already registered to someone else stays theirs
    (signing out removes the device's subscription in the browser, which ends that)."""
    with user_session(user.id) as session:
        session.execute(
            text(
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)"
                " VALUES (:u, :endpoint, :p256dh, :auth) ON CONFLICT (endpoint) DO NOTHING"
            ),
            {
                "u": user.id,
                "endpoint": body.endpoint,
                "p256dh": body.keys.p256dh,
                "auth": body.keys.auth,
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/push-subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscription(endpoint: Annotated[str, Query()], user: SignedInUser) -> Response:
    with user_session(user.id) as session:
        session.execute(
            text("DELETE FROM push_subscriptions WHERE user_id = :u AND endpoint = :endpoint"),
            {"u": user.id, "endpoint": endpoint},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
