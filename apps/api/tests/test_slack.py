"""P2-07: Slack (ADR-040). A new lead, a hold request and a handoff post to the tenant's channel;
`/lot` answers with the current price; a bad signature is rejected; a tenant without Slack sends
nothing. Slack itself is replaced by a fake: no test reaches slack.com."""

import hashlib
import hmac
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from cornerpin.core.config import get_settings
from cornerpin.core.db import user_session, worker_session
from cornerpin.core.outbox import drain
from cornerpin.integrations import slack
from cornerpin.integrations.base import Activity
from cornerpin.integrations.crypto import Unsealable, seal, unseal

from .conftest import Databases, Listing, TenantData
from .outreach_support import TURNSTILE, email_of, inquire, lead_of

SIGNING_SECRET = "slack-signing-secret-for-tests"  # noqa: S105 -- a test value
TEAM = "T0TEST"
WRONG_SECRET = "not-slacks"  # noqa: S105 -- a test value
WEBHOOK = "https://hooks.slack.test/services/T0TEST/B0TEST/abc123"


@dataclass
class FakeSlack:
    posts: list[tuple[str, dict[str, Any]]] = field(default_factory=lambda: [])
    codes: list[str] = field(default_factory=lambda: [])
    reply: tuple[int, str] = (200, "ok")
    answer: dict[str, Any] = field(
        default_factory=lambda: {
            "ok": True,
            "team": {"id": TEAM, "name": "Demo Land Co."},
            "incoming_webhook": {"channel": "#lots", "channel_id": "C0LOTS", "url": WEBHOOK},
        }
    )

    def exchange(self, code: str, redirect_uri: str) -> dict[str, Any]:
        assert redirect_uri == "http://localhost:3300/v1/integrations/slack/callback"
        self.codes.append(code)
        return self.answer

    def post(self, webhook_url: str, payload: dict[str, Any]) -> tuple[int, str]:
        self.posts.append((webhook_url, payload))
        return self.reply

    def texts(self) -> list[str]:
        return [payload["text"] for _, payload in self.posts]


@pytest.fixture
def fake_slack(
    db: Databases, tenants: tuple[TenantData, TenantData], monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeSlack]:
    """Cornerpin's Slack app configured, Slack faked; alpha's connection put back after."""
    monkeypatch.setenv("SLACK_CLIENT_ID", "1234.5678")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
    get_settings.cache_clear()
    fake = FakeSlack()
    monkeypatch.setattr(slack, "get_slack_api", lambda: fake)
    drain()
    yield fake
    with db.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE integration_connections SET status = 'connecting', enabled = false,"
                " settings = '{}', secret = NULL, error = NULL WHERE tenant_id = :t"
            ),
            {"t": tenants[0].tenant_id},
        )
    get_settings.cache_clear()


def connect(client: TestClient, tenant_id: UUID) -> None:
    """Connect a tenant the local way, with a webhook made by hand."""
    connected = client.post(
        "/v1/dev/integrations/slack",
        json={"tenant_id": str(tenant_id), "webhook_url": WEBHOOK, "team_id": TEAM},
    )
    assert connected.status_code == 204, connected.text


def lead_activity_events(db: Databases) -> int:
    with db.owner.connect() as conn:
        count: int = conn.execute(
            text("SELECT count(*) FROM outbox WHERE event_type = 'integrations.lead_activity'")
        ).scalar_one()
    return count


def signed(body: str, *, secret: str = SIGNING_SECRET, at: int | None = None) -> dict[str, str]:
    stamp = str(at if at is not None else int(time.time()))
    mac = hmac.new(secret.encode(), f"v0:{stamp}:{body}".encode(), hashlib.sha256).hexdigest()
    return {
        "x-slack-request-timestamp": stamp,
        "x-slack-signature": f"v0={mac}",
        "content-type": "application/x-www-form-urlencoded",
    }


def command(client: TestClient, words: str, *, team: str = TEAM, **sign: Any) -> Any:
    body = urlencode({"command": "/lot", "text": words, "team_id": team, "user_id": "U1"})
    return client.post(
        "/v1/integrations/slack/commands", content=body, headers=signed(body, **sign)
    )


def slack_of(integrations: list[dict[str, Any]]) -> dict[str, Any]:
    return next(i for i in integrations if i["provider"] == "slack")


def slug_of(db: Databases, listing: Listing) -> str:
    with db.owner.connect() as conn:
        slug: str = conn.execute(
            text("SELECT slug FROM subdivisions WHERE id = :id"), {"id": listing.subdivision_id}
        ).scalar_one()
    return slug


# --- without a database -----------------------------------------------------------------------


def test_credentials_are_sealed_to_their_tenant_and_provider() -> None:
    tenant = uuid4()
    sealed = seal(tenant, "slack", {"webhook_url": WEBHOOK})
    assert WEBHOOK.encode() not in sealed
    assert unseal(tenant, "slack", sealed) == {"webhook_url": WEBHOOK}
    with pytest.raises(Unsealable):
        unseal(uuid4(), "slack", sealed)  # copied to another tenant
    with pytest.raises(Unsealable):
        unseal(tenant, "salesforce", sealed)
    with pytest.raises(Unsealable):
        unseal(tenant, "slack", sealed[:-1] + bytes([sealed[-1] ^ 1]))


def test_slack_signatures_cover_the_body_and_the_time() -> None:
    now = time.time()
    stamp = str(int(now))
    body = b"text=Buyers+1&team_id=T0TEST"
    good = (
        "v0="
        + hmac.new(
            SIGNING_SECRET.encode(), f"v0:{stamp}:".encode() + body, hashlib.sha256
        ).hexdigest()
    )
    assert slack.verify_signature(SIGNING_SECRET, stamp, good, body, now)
    assert not slack.verify_signature(SIGNING_SECRET, stamp, good, body + b"x", now)
    assert not slack.verify_signature("another-secret", stamp, good, body, now)
    assert not slack.verify_signature(SIGNING_SECRET, stamp, good, body, now + 301)
    assert not slack.verify_signature(SIGNING_SECRET, "soon", good, body, now)


def test_alerts_escape_what_buyers_wrote() -> None:
    lead = Activity(
        id=uuid4(),
        tenant_id=uuid4(),
        lead_id=uuid4(),
        kind="inquiry",
        new_lead=True,
        verified=False,
        buyer="Pat <@channel>",
        message="Is it flat?\n<https://evil.test|click> & more",
        reason=None,
        lot="Lot 1, Buyers",
        lot_url="http://localhost:3300/buyers/lots/1",
        lead_url="http://localhost:3300/app/t/leads/l",
        name="Pat <@channel>",
        email="pat@example.test",
        phone=None,
        stage="new",
        hold_request_id=None,
        lot_price=None,
        decided_at=None,
    )
    assert slack.alert_text(lead) == (
        "*New lead:* Pat &lt;@channel&gt; (email not verified) asked about"
        " <http://localhost:3300/buyers/lots/1|Lot 1, Buyers>\n"
        ">Is it flat?\n"
        ">&lt;https://evil.test|click&gt; &amp; more\n"
        "<http://localhost:3300/app/t/leads/l|Open the lead in Cornerpin>"
    )
    # A returning lead's inquiry isn't news; owners asked for new leads.
    assert slack.alert_text(replace(lead, new_lead=False)) is None


# --- connecting ---------------------------------------------------------------------------------


def test_slack_is_dormant_until_it_is_set_up(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    base = f"/v1/tenants/{tenants[0].tenant_id}/integrations"
    listed = slack_of(alpha_owner.get(base).json())
    assert (listed["provider"], listed["available"]) == ("slack", False)
    assert alpha_owner.get(f"{base}/slack/install", follow_redirects=False).status_code == 404
    assert alpha_owner.post("/v1/integrations/slack/commands", content="").status_code == 404


def test_an_owner_adds_slack_and_never_sees_its_secret(
    fake_slack: FakeSlack, alpha_owner: TestClient, tenants: tuple[TenantData, TenantData],
    db: Databases,
) -> None:  # fmt: skip
    alpha = tenants[0]
    base = f"/v1/tenants/{alpha.tenant_id}/integrations"
    sent = alpha_owner.get(f"{base}/slack/install", follow_redirects=False)
    assert sent.status_code == 303
    to_slack = urlparse(sent.headers["location"])
    query = {k: v[0] for k, v in parse_qs(to_slack.query).items()}
    assert to_slack.netloc == "slack.com"
    assert (query["client_id"], query["scope"]) == ("1234.5678", "incoming-webhook,commands")

    back = alpha_owner.get(
        "/v1/integrations/slack/callback",
        params={"code": "one-time-code", "state": query["state"]},
        follow_redirects=False,
    )
    assert back.status_code == 303
    page = f"/app/{alpha.tenant_id}/integrations?slack=connecting"
    assert back.headers["location"].endswith(page)
    connecting = slack_of(alpha_owner.get(base).json())
    assert connecting["status"] == "connecting"

    drain()  # the worker exchanges the code
    assert fake_slack.codes == ["one-time-code"]
    connected = slack_of(alpha_owner.get(base).json())
    assert {k: connected[k] for k in ("status", "enabled", "account", "channel")} == {
        "status": "connected",
        "enabled": True,
        "account": "Demo Land Co.",
        "channel": "#lots",
    }
    assert "secret" not in connected and WEBHOOK not in str(connected)

    with db.owner.connect() as conn:
        stored = conn.execute(
            text("SELECT secret FROM integration_connections WHERE tenant_id = :t"),
            {"t": alpha.tenant_id},
        ).scalar_one()
        code_left = conn.execute(
            text(
                "SELECT count(*) FROM outbox WHERE event_type = 'integrations.slack_connect'"
                " AND payload ? 'code'"
            )
        ).scalar_one()
    assert WEBHOOK.encode() not in bytes(stored)
    assert unseal(alpha.tenant_id, "slack", bytes(stored)) == {"webhook_url": WEBHOOK}
    assert code_left == 0  # the code left the outbox once used

    # Not even the database lets an owner read the sealed value.
    with (
        pytest.raises(ProgrammingError, match="permission denied"),
        user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
    ):
        session.execute(text("SELECT secret FROM integration_connections"))

    # Switched off, then removed.
    assert alpha_owner.patch(f"{base}/slack", json={"enabled": False}).json()["enabled"] is False
    assert alpha_owner.delete(f"{base}/slack").status_code == 204
    assert slack_of(alpha_owner.get(base).json())["status"] == "not_connected"
    with db.owner.begin() as conn:  # put back the row the fixtures expect
        conn.execute(
            text("INSERT INTO integration_connections (tenant_id, provider) VALUES (:t, 'slack')"),
            {"t": alpha.tenant_id},
        )


def test_an_install_only_finishes_for_whoever_started_it(
    fake_slack: FakeSlack, alpha_owner: TestClient, buyer: TestClient,
    tenants: tuple[TenantData, TenantData],
) -> None:  # fmt: skip
    alpha = tenants[0]
    sent = alpha_owner.get(
        f"/v1/tenants/{alpha.tenant_id}/integrations/slack/install", follow_redirects=False
    )
    state = parse_qs(urlparse(sent.headers["location"]).query)["state"][0]

    stolen = buyer.get(
        "/v1/integrations/slack/callback",
        params={"code": "c", "state": state},
        follow_redirects=False,
    )
    assert stolen.status_code == 400
    forged = alpha_owner.get(
        "/v1/integrations/slack/callback",
        params={"code": "c", "state": state[:-2] + "xx"},
        follow_redirects=False,
    )
    assert forged.status_code == 400
    cancelled = alpha_owner.get(
        "/v1/integrations/slack/callback",
        params={"error": "access_denied", "state": state},
        follow_redirects=False,
    )
    assert cancelled.headers["location"].endswith("?slack=cancelled")
    assert fake_slack.codes == []


# --- alerts ---------------------------------------------------------------------------------------


def test_new_leads_holds_and_handoffs_post_to_the_channel(
    fake_slack: FakeSlack, alpha_owner: TestClient, buyer: TestClient, anonymous: TestClient,
    listing: Listing, db: Databases,
) -> None:  # fmt: skip
    connect(alpha_owner, listing.tenant.tenant_id)

    inquire(buyer, listing, allow_email=True)
    drain()
    [(url, payload)] = fake_slack.posts
    assert url == WEBHOOK
    assert payload["text"].startswith("*New lead:* Pat Buyer asked about <http://localhost:3300/")
    assert "|Lot 1, Buyers>\n>Is the well shared?\n<http://localhost:3300/app/" in payload["text"]

    inquire(buyer, listing, allow_email=True, message="And the HOA?")
    drain()
    assert len(fake_slack.posts) == 1  # the same lead again: not new

    held = buyer.post(f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat Buyer"})
    assert held.status_code == 201, held.text
    lead_id = lead_of(db, listing, email_of(buyer))
    with worker_session(engine=db.api) as session:  # as the agent hands off
        session.execute(
            text(
                "UPDATE leads SET handoff_at = now(), handoff_reason = 'Asked about financing'"
                " WHERE id = :id"
            ),
            {"id": lead_id},
        )
    drain()
    assert [t.split("\n")[0] for t in fake_slack.texts()[1:]] == [
        f"*Hold request:* Pat Buyer asked to hold <http://localhost:3300/{slug_of(db, listing)}"
        "/lots/1|Lot 1, Buyers>",
        "*Needs a person:* Pat Buyer",
    ]
    assert "Asked about financing" in fake_slack.texts()[2]

    walk_in = f"walkin-{uuid4().hex[:6]}@example.test"
    asked = anonymous.post(
        f"/v1/lots/{listing.available}/inquiries",
        json={"name": "Walk In", "email": walk_in, "message": "Hi", **TURNSTILE},
    )
    assert asked.status_code == 201, asked.text
    drain()
    assert "Walk In (email not verified) asked about" in fake_slack.texts()[-1]


def test_a_tenant_without_slack_sends_nothing(
    fake_slack: FakeSlack, alpha_owner: TestClient, buyer: TestClient, listing: Listing,
    db: Databases,
) -> None:  # fmt: skip
    queued = lead_activity_events(db)
    inquire(buyer, listing, allow_email=False)  # alpha has a Slack row, but not connected
    drain()
    assert lead_activity_events(db) == queued  # not even queued
    assert fake_slack.posts == []

    connect(alpha_owner, listing.tenant.tenant_id)
    base = f"/v1/tenants/{listing.tenant.tenant_id}/integrations/slack"
    assert alpha_owner.patch(base, json={"enabled": False}).status_code == 200
    inquire(alpha_owner, listing, allow_email=False)
    drain()
    assert lead_activity_events(db) == queued  # switched off
    assert fake_slack.posts == []


def test_a_dead_webhook_marks_the_connection_failed(
    fake_slack: FakeSlack, alpha_owner: TestClient, buyer: TestClient, listing: Listing,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    connect(alpha_owner, listing.tenant.tenant_id)
    fake_slack.reply = (404, "no_service")
    with caplog.at_level(logging.WARNING):
        inquire(buyer, listing, allow_email=False)
        drain()
    slack_row = slack_of(
        alpha_owner.get(f"/v1/tenants/{listing.tenant.tenant_id}/integrations").json()
    )
    assert slack_row["status"] == "failed"
    assert slack_row["error"] == "Slack stopped accepting alerts (no_service). Add it again."
    assert "slack connection" in caplog.text
    assert len(fake_slack.posts) == 1  # not retried


# --- /lot -----------------------------------------------------------------------------------------


def test_lot_answers_with_the_current_price(
    fake_slack: FakeSlack, alpha_owner: TestClient, anonymous: TestClient, listing: Listing,
    db: Databases,
) -> None:  # fmt: skip
    connect(alpha_owner, listing.tenant.tenant_id)
    slug = slug_of(db, listing)

    answer = command(anonymous, f"{slug} 1")
    assert answer.status_code == 200
    assert answer.json() == {
        "response_type": "ephemeral",
        "text": f"<http://localhost:3300/{slug}/lots/1|Lot 1, Buyers>: available, $90,000",
    }
    sold = command(anonymous, f"{slug} 2").json()["text"]
    assert sold.endswith("Lot 2, Buyers>: sold, $90,000")
    assert command(anonymous, f"{slug} 3").json()["text"] == (
        "Lot 3, Buyers: available, $90,000 (not published)"
    )

    # The price changes; the next answer has it.
    with db.owner.begin() as conn:
        conn.execute(
            text("UPDATE lots SET price = 95500 WHERE id = :id"), {"id": listing.available}
        )
    assert command(anonymous, f"{slug} 1").json()["text"].endswith("available, $95,500")

    assert command(anonymous, f"{slug} 99").json()["text"].startswith(f"No lot 99 in {slug}.")
    assert command(anonymous, "").json()["text"].startswith("Try `/lot <subdivision>")
    # Another tenant's lot isn't this workspace's to see.
    assert command(anonymous, "bravo-subdivision 1").json()["text"].startswith("No lot 1")
    other = command(anonymous, f"{slug} 1", team="T0OTHER").json()["text"]
    assert other.startswith("This Slack workspace isn't connected to Cornerpin.")


def test_lot_rejects_a_bad_signature(
    fake_slack: FakeSlack, anonymous: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert command(anonymous, "x 1", secret=WRONG_SECRET).status_code == 401
        assert command(anonymous, "x 1", at=int(time.time()) - 600).status_code == 401
        unsigned = anonymous.post(
            "/v1/integrations/slack/commands",
            content="text=x+1",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        assert unsigned.status_code == 401
    assert caplog.text.count("rejected a Slack request: missing or bad signature") == 3
