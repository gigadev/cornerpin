"""Integrations in the owner portal (P2-07, ADR-040), Slack's install callback and slash
command, and a local-only way to connect Slack with a hand-made webhook.

Owners and staff see a connection's status, workspace and channel, switch it on or off, and
remove it; they never see its credentials. Adding Slack sends them to Slack and back; the code
Slack returns is exchanged by the worker."""

import json
import time
from typing import Any, Literal
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import text

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.config import get_settings
from cornerpin.core.db import worker_session
from cornerpin.core.outbox import enqueue
from cornerpin.core.tenancy import tenant_session
from cornerpin.integrations import slack
from cornerpin.integrations.crypto import seal
from cornerpin.integrations.events import SlackConnect

router = APIRouter(tags=["integrations"])
hidden = APIRouter(include_in_schema=False)

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}

IntegrationStatus = Literal["not_connected", "connecting", "connected", "failed"]


class Integration(BaseModel):
    provider: Literal["slack"]
    available: bool = Field(description="Set up on this Cornerpin, so it can be connected")
    status: IntegrationStatus
    enabled: bool = Field(description="Alerts are on")
    workspace: str | None
    channel: str | None
    error: str | None = Field(description="Why a connection failed, for the owner")


class IntegrationUpdate(BaseModel):
    enabled: bool


CONNECTION = """
    SELECT enabled, status, error, settings FROM integration_connections
    WHERE tenant_id = app_tenant_id() AND provider = 'slack'
"""


def _slack(row: Any) -> Integration:
    settings: dict[str, Any] = row.settings if row else {}
    return Integration(
        provider="slack",
        available=get_settings().slack_enabled,
        status=row.status if row else "not_connected",
        enabled=bool(row and row.enabled),
        workspace=settings.get("team_name"),
        channel=settings.get("channel"),
        error=row.error if row else None,
    )


@router.get("/tenants/{tenant_id}/integrations", responses=NOT_FOUND)
def list_integrations(tenant_id: UUID, user: SignedInUser) -> list[Integration]:
    with tenant_session(user, tenant_id) as session:
        return [_slack(session.execute(text(CONNECTION)).one_or_none())]


@router.get(
    "/tenants/{tenant_id}/integrations/slack/install",
    status_code=status.HTTP_303_SEE_OTHER,
    responses=NOT_FOUND,
)
def install_slack(tenant_id: UUID, user: SignedInUser) -> RedirectResponse:
    """Send the owner to Slack to add Cornerpin's app and pick a channel."""
    if not get_settings().slack_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slack isn't set up on this Cornerpin")
    with tenant_session(user, tenant_id):
        pass  # a member of this tenant
    return RedirectResponse(slack.install_url(tenant_id, user.id), status.HTTP_303_SEE_OTHER)


@router.patch("/tenants/{tenant_id}/integrations/slack", responses=NOT_FOUND)
def update_slack(tenant_id: UUID, body: IntegrationUpdate, user: SignedInUser) -> Integration:
    """Switch alerts on or off; the connection stays."""
    with tenant_session(user, tenant_id) as session:
        changed = session.execute(
            text(
                "UPDATE integration_connections SET enabled = :on"
                " WHERE tenant_id = app_tenant_id() AND provider = 'slack' RETURNING id"
            ),
            {"on": body.enabled},
        ).first()
        if changed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Slack isn't connected")
        return _slack(session.execute(text(CONNECTION)).one())


@router.delete(
    "/tenants/{tenant_id}/integrations/slack",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
def remove_slack(tenant_id: UUID, user: SignedInUser) -> Response:
    """Forget the connection and its webhook. Removing the app from the workspace is done in
    Slack."""
    with tenant_session(user, tenant_id) as session:
        session.execute(
            text(
                "DELETE FROM integration_connections"
                " WHERE tenant_id = app_tenant_id() AND provider = 'slack'"
            )
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Slack's side -------------------------------------------------------------------------------


@hidden.get("/integrations/slack/callback")
def slack_callback(
    user: SignedInUser, state: str, code: str | None = None, error: str | None = None
) -> RedirectResponse:
    """Slack sends the owner back here. The code is queued for the worker to exchange."""
    tenant_id = slack.tenant_of_state(state, user.id)
    if tenant_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This link has expired. Add Slack again from Integrations."
        )
    page = f"{get_settings().web_origin}/app/{tenant_id}/integrations"
    if error or not code:
        return RedirectResponse(f"{page}?slack=cancelled", status.HTTP_303_SEE_OTHER)
    with tenant_session(user, tenant_id) as session:
        session.execute(
            text(
                "INSERT INTO integration_connections (tenant_id, provider, status, enabled)"
                " VALUES (app_tenant_id(), 'slack', 'connecting', false)"
                " ON CONFLICT (tenant_id, provider)"
                " DO UPDATE SET status = 'connecting', error = NULL"
            )
        )
        enqueue(session, SlackConnect(tenant_id=tenant_id, code=code))
    return RedirectResponse(f"{page}?slack=connecting", status.HTTP_303_SEE_OTHER)


@hidden.post("/integrations/slack/commands")
async def slack_command(request: Request) -> Response:
    """`/lot <subdivision> <number>`. Slack signs the raw form body; it's checked before it's
    read. Answers go only to whoever asked."""
    secret = get_settings().slack_signing_secret
    if not secret:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    body = await request.body()
    if not slack.verify_signature(
        secret,
        request.headers.get("x-slack-request-timestamp", ""),
        request.headers.get("x-slack-signature", ""),
        body,
        time.time(),
    ):
        slack.log_rejected("missing or bad signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad signature")
    form = parse_qs(body.decode())
    team = (form.get("team_id") or [""])[0]
    words = (form.get("text") or [""])[0]

    def answer() -> str:
        with worker_session() as session:
            return slack.lot_answer(session, team, words)

    return JSONResponse({"response_type": "ephemeral", "text": await run_in_threadpool(answer)})


class DevSlackConnection(BaseModel):
    tenant_id: UUID
    webhook_url: HttpUrl
    team_id: str = "T0LOCAL"
    team_name: str = "Local workspace"
    channel: str = "#cornerpin"


@hidden.post("/dev/integrations/slack", status_code=status.HTTP_204_NO_CONTENT)
def dev_connect_slack(body: DevSlackConnection) -> Response:
    """Local only: connect a tenant to a webhook made by hand in Slack, since Slack won't send
    an install back to http://localhost. The same handlers then post to it."""
    if not get_settings().is_local:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    settings = {"team_id": body.team_id, "team_name": body.team_name, "channel": body.channel}
    with worker_session() as session:
        session.execute(
            text(
                "INSERT INTO integration_connections"
                " (tenant_id, provider, status, enabled, settings, secret)"
                " VALUES (:t, 'slack', 'connected', true, CAST(:s AS jsonb), :secret)"
                " ON CONFLICT (tenant_id, provider) DO UPDATE SET status = 'connected',"
                " enabled = true, error = NULL, settings = EXCLUDED.settings,"
                " secret = EXCLUDED.secret"
            ),
            {
                "t": body.tenant_id,
                "s": json.dumps(settings),
                "secret": seal(
                    body.tenant_id, slack.PROVIDER, {"webhook_url": str(body.webhook_url)}
                ),
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
