"""Inbound email (P2-04, ADR-037): Resend's webhook, and a local route that feeds the same
handler. The API is private, so the webhook arrives through the web app's /v1 proxy."""

import base64
import hashlib
import hmac
import logging
import time
from collections.abc import Mapping
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from cornerpin.core.config import get_settings
from cornerpin.core.db import worker_session
from cornerpin.core.fields import EmailAddress
from cornerpin.core.outbox import enqueue
from cornerpin.outreach.events import InboundEmailReceived

logger = logging.getLogger(__name__)
router = APIRouter(tags=["outreach"], include_in_schema=False)

# Svix, which signs Resend's webhooks, rejects anything older or newer than this.
TOLERANCE_SECONDS = 5 * 60


def verify_svix(secret: str, headers: Mapping[str, str], body: bytes, now: float) -> bool:
    """Svix's scheme: base64 HMAC-SHA256 of "id.timestamp.body", keyed with the secret after
    "whsec_"; the signature header lists one or more "v1,<signature>"."""
    message_id = headers.get("svix-id")
    timestamp = headers.get("svix-timestamp")
    signatures = headers.get("svix-signature")
    if not (message_id and timestamp and signatures):
        return False
    try:
        if abs(now - int(timestamp)) > TOLERANCE_SECONDS:
            return False
        key = base64.b64decode(secret.removeprefix("whsec_"))
    except ValueError:
        return False
    signed = f"{message_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return any(
        hmac.compare_digest(expected, candidate.partition(",")[2])
        for candidate in signatures.split()
        if candidate.startswith("v1,")
    )


class _Received(BaseModel):
    email_id: str
    from_: str = Field(alias="from")
    to: list[str]
    subject: str | None = None


class _ResendEvent(BaseModel):
    type: str
    data: _Received | None = None


def _queue(event: InboundEmailReceived) -> None:
    with worker_session() as session:
        enqueue(session, event)


@router.post("/webhooks/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_webhook(request: Request) -> Response:
    secret = get_settings().resend_webhook_secret
    if not secret:  # dormant until the webhook exists (ADR-012)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    body = await request.body()
    if not verify_svix(secret, request.headers, body, time.time()):
        logger.warning("rejected a Resend webhook: missing or bad signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    try:
        event = _ResendEvent.model_validate_json(body)
    except ValidationError:
        logger.warning("rejected a signed Resend webhook: unexpected payload")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unexpected payload") from None
    if event.type == "email.received" and event.data is not None:
        await run_in_threadpool(
            _queue,
            InboundEmailReceived(
                provider="resend",
                provider_email_id=event.data.email_id,
                to=event.data.to,
                from_address=event.data.from_,
                subject=event.data.subject,
            ),
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class DevInboundEmail(BaseModel):
    to: str
    from_address: EmailAddress
    subject: str | None = None
    text: str


@router.post("/dev/inbound-email", status_code=status.HTTP_204_NO_CONTENT)
def dev_inbound_email(body: DevInboundEmail) -> Response:
    """Local only: a reply as if the provider had received it, through the same handler."""
    if not get_settings().is_local:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    _queue(
        InboundEmailReceived(
            provider="dev",
            provider_email_id=uuid4().hex,
            to=[body.to],
            from_address=body.from_address,
            subject=body.subject,
            text=body.text,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
