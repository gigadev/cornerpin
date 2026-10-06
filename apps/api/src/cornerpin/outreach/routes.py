"""Unsubscribing from an owner's outreach (ADR-036), from the link in every outreach email."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from cornerpin.core.db import user_session
from cornerpin.leads import consent
from cornerpin.leads.schemas import Channel
from cornerpin.outreach.unsubscribe import read_token

router = APIRouter(prefix="/unsubscribe", tags=["outreach"])

BAD_LINK: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"description": "The link was altered or no longer works"}
}


class Unsubscribe(BaseModel):
    tenant_name: str
    channel: Channel
    allowed: bool


def _state(token: str, *, opt_out: bool) -> Unsubscribe:
    read = read_token(token)
    if read is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link doesn't work")
    tenant_id, user_id, channel = read
    # The signed link stands in for signing in, for this one choice.
    with user_session(user_id) as session:
        name = session.execute(
            text("SELECT name FROM tenants WHERE id = :id"), {"id": tenant_id}
        ).scalar_one_or_none()
        if name is None:  # the account or the owner is gone, or never had permission
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link doesn't work")
        allowed = consent.current_choices(session, tenant_id, user_id).model_dump().get(channel)
        if opt_out and allowed:
            consent.record(session, tenant_id, user_id, channel, False, "unsubscribe")
            allowed = False
    return Unsubscribe(tenant_name=name, channel=channel, allowed=bool(allowed))


@router.get("", responses=BAD_LINK)
def unsubscribe_page(token: str) -> Unsubscribe:
    """What the link would stop, without changing anything (mail scanners open links)."""
    return _state(token, opt_out=False)


@router.post("", responses=BAD_LINK)
def unsubscribe(token: str) -> Unsubscribe:
    """Stop this owner contacting this buyer on this channel. Also the one-click target
    (RFC 8058); its form body is ignored."""
    return _state(token, opt_out=True)
