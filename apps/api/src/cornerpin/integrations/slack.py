"""Slack (P2-07, ADR-040): alerts to the channel an owner picked when they added Cornerpin's app,
and `/lot <subdivision> <number>` answered from the database.

Connecting is Slack's OAuth: the owner is sent to Slack with a signed state naming the tenant
and themselves; Slack sends them back with a one-time code, which the worker exchanges for the
channel's webhook URL. Calls to Slack happen only in outbox handlers (ADR-010). Requests from
Slack carry a signature over the raw body, checked before anything is read."""

import hashlib
import hmac
import json
import logging
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.tokens import sign, unsign
from cornerpin.core.config import get_settings
from cornerpin.integrations.base import Activity, Broken, Connection
from cornerpin.integrations.crypto import seal
from cornerpin.listings.models import LotStatus
from cornerpin.outreach.tools import money

logger = logging.getLogger(__name__)

PROVIDER = "slack"
SCOPES = "incoming-webhook,commands"
AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
OAUTH_ACCESS_URL = "https://slack.com/api/oauth.v2.access"
STATE_MAX_AGE_SECONDS = 15 * 60
SIGNATURE_TOLERANCE_SECONDS = 300
# Webhook answers that mean the connection is dead, not busy.
GONE = {
    "no_service",
    "no_active_hooks",
    "channel_not_found",
    "channel_is_archived",
    "invalid_token",
    "team_disabled",
    "action_prohibited",
}
STATUS_WORDS = {
    LotStatus.AVAILABLE: "available",
    LotStatus.ON_HOLD: "on hold",
    LotStatus.SOLD: "sold",
}


# --- talking to Slack ------------------------------------------------------------------------


class SlackApi(Protocol):
    def exchange(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """oauth.v2.access: Slack's answer, ok or not."""
        ...

    def post(self, webhook_url: str, payload: dict[str, Any]) -> tuple[int, str]:
        """Post to an incoming webhook: (HTTP status, body)."""
        ...


class HttpSlackApi:
    def exchange(self, code: str, redirect_uri: str) -> dict[str, Any]:
        settings = get_settings()
        response = httpx.post(
            OAUTH_ACCESS_URL,
            data={"code": code, "redirect_uri": redirect_uri},
            auth=(settings.slack_client_id or "", settings.slack_client_secret or ""),
            timeout=15,
        )
        response.raise_for_status()
        answer: dict[str, Any] = response.json()
        return answer

    def post(self, webhook_url: str, payload: dict[str, Any]) -> tuple[int, str]:
        response = httpx.post(webhook_url, json=payload, timeout=15)
        return response.status_code, response.text.strip()


def get_slack_api() -> SlackApi:
    return HttpSlackApi()


# --- connecting ------------------------------------------------------------------------------


def redirect_uri() -> str:
    """Where Slack sends the owner back: the API, through the web app's /v1 proxy."""
    return f"{get_settings().web_origin}/v1/integrations/slack/callback"


def install_url(tenant_id: UUID, user_id: UUID) -> str:
    settings = get_settings()
    state = sign({"t": str(tenant_id), "u": str(user_id)}, settings.secret_key)
    query = urlencode(
        {
            "client_id": settings.slack_client_id,
            "scope": SCOPES,
            "redirect_uri": redirect_uri(),
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def tenant_of_state(state: str, user_id: UUID) -> UUID | None:
    """The tenant an install was started for, if this signed-in user started it, recently."""
    value = unsign(state, get_settings().secret_key, max_age_seconds=STATE_MAX_AGE_SECONDS)
    if value is None or value.get("u") != str(user_id):
        return None
    try:
        return UUID(value["t"])
    except (KeyError, ValueError):
        return None


def connect(session: Session, tenant_id: UUID, code: str) -> None:
    """Exchange the install's code for the channel's webhook, and seal it on the connection.
    A connection removed in the meantime stays removed."""
    answer = get_slack_api().exchange(code, redirect_uri())
    hook: dict[str, Any] = answer.get("incoming_webhook") or {}
    team: dict[str, Any] = answer.get("team") or {}
    if not answer.get("ok") or not hook.get("url"):
        problem = answer.get("error") or "no channel was chosen"
        session.execute(
            text(
                "UPDATE integration_connections SET status = 'failed', error = :e"
                " WHERE tenant_id = :t AND provider = 'slack'"
            ),
            {"t": tenant_id, "e": f"Slack didn't connect ({problem}). Try adding it again."},
        )
        return
    settings = {
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "channel": hook.get("channel"),
        "channel_id": hook.get("channel_id"),
    }
    session.execute(
        text(
            "UPDATE integration_connections SET status = 'connected', enabled = true,"
            " error = NULL, settings = CAST(:settings AS jsonb), secret = :secret"
            " WHERE tenant_id = :t AND provider = 'slack'"
        ),
        {
            "t": tenant_id,
            "settings": json.dumps(settings),
            "secret": seal(tenant_id, PROVIDER, {"webhook_url": hook["url"]}),
        },
    )


# --- alerts ------------------------------------------------------------------------------------


def escape(words: str) -> str:
    """Slack's three control characters, so a buyer can't write links or mentions."""
    return words.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def alert_text(activity: Activity) -> str | None:
    """The message for an activity, or None when it isn't one owners asked to hear about
    (an inquiry from a lead they already have)."""
    who = escape(activity.buyer) + ("" if activity.verified else " (email not verified)")
    lot = escape(activity.lot or "a lot")
    if activity.lot and activity.lot_url:
        lot = f"<{activity.lot_url}|{lot}>"
    match activity.kind:
        case "inquiry" if activity.new_lead:
            lines = [f"*New lead:* {who} asked about {lot}"]
        case "hold_requested":
            lines = [f"*Hold request:* {who} asked to hold {lot}"]
        case "handoff":
            lines = [f"*Needs a person:* {who}"]
            if activity.reason:
                lines.append(escape(activity.reason[:500]))
        case _:
            return None
    if activity.message and activity.kind != "handoff":
        lines += [f">{escape(line)}" for line in activity.message[:500].splitlines() if line]
    lines.append(f"<{activity.lead_url}|Open the lead in Cornerpin>")
    return "\n".join(lines)


class SlackAdapter:
    provider = PROVIDER

    def wants(self, activity: Activity) -> bool:
        return alert_text(activity) is not None

    def deliver(self, connection: Connection, activity: Activity) -> None:
        message = alert_text(activity)
        if message is None:
            return
        status, body = get_slack_api().post(
            connection.secret["webhook_url"], {"text": message, "unfurl_links": False}
        )
        if status == 200:
            return
        if status in (403, 404, 410) or body in GONE:
            raise Broken(f"Slack stopped accepting alerts ({body or status}). Add it again.")
        raise RuntimeError(f"Slack answered {status}: {body[:200]}")


# --- requests from Slack ----------------------------------------------------------------------


def verify_signature(secret: str, timestamp: str, signature: str, body: bytes, now: float) -> bool:
    """Slack's v0 signature: HMAC-SHA256 of "v0:<timestamp>:<body>", within five minutes."""
    if not timestamp.isdigit() or abs(now - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


USAGE = "Try `/lot <subdivision> <lot number>`, for example `/lot Juniper Bench 2-6`."


def lot_answer(session: Session, team_id: str, words: str) -> str:
    """The answer to `/lot`, for the tenants this Slack workspace is connected to, whether or
    not their alerts are switched on."""
    tenants = list(
        session.execute(
            text(
                "SELECT tenant_id FROM integration_connections WHERE provider = 'slack'"
                " AND status = 'connected' AND settings->>'team_id' = :team"
            ),
            {"team": team_id},
        ).scalars()
    )
    if not tenants:
        return (
            "This Slack workspace isn't connected to Cornerpin. An owner can add it from"
            " Integrations in the owner portal."
        )
    parts = words.split()
    if not parts:
        return USAGE
    number, subdivision = parts[-1], " ".join(parts[:-1]) or None
    rows = session.execute(
        text(
            "SELECT l.number, l.status, l.price, l.published AND s.published AS public,"
            " s.name AS subdivision, s.slug FROM lots l"
            " JOIN subdivisions s ON s.id = l.subdivision_id"
            " WHERE l.tenant_id = ANY(:tenants) AND lower(l.number) = lower(:number)"
            " AND (CAST(:sub AS text) IS NULL OR s.name ILIKE :sub OR s.slug = lower(:sub))"
            " ORDER BY s.name LIMIT 6"
        ),
        {"tenants": tenants, "number": number, "sub": subdivision},
    ).all()
    where = f" in {escape(subdivision)}" if subdivision else ""
    if not rows:
        return f"No lot {escape(number)}{where}. {USAGE}"
    if len(rows) > 1:
        names = ", ".join(escape(row.subdivision) for row in rows[:5])
        return f"Lot {escape(number)} is in more than one subdivision ({names}). {USAGE}"
    row = rows[0]
    price = money(row.price) if row.price is not None else "no price set"
    name = f"Lot {escape(row.number)}, {escape(row.subdivision)}"
    if row.public:
        name = f"<{get_settings().web_origin}/{row.slug}/lots/{row.number}|{name}>"
    hidden = "" if row.public else " (not published)"
    return f"{name}: {STATUS_WORDS[LotStatus(row.status)]}, {price}{hidden}"


def log_rejected(reason: str) -> None:
    logger.warning("rejected a Slack request: %s", reason)
