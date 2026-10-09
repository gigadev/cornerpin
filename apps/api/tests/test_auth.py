"""P1-03: magic-link sign-in through the outbox, sessions, Turnstile, dormant Google sign-in,
and owners kept to their own tenant."""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.auth.google import GoogleIdentity, get_google
from cornerpin.core.auth.turnstile import get_turnstile
from cornerpin.core.config import get_settings
from cornerpin.core.outbox import process_pending
from cornerpin.main import create_app
from cornerpin.notifications import handlers
from cornerpin.notifications.email import Email

from .conftest import Databases, TenantData


@dataclass
class FakeTurnstile:
    ok: bool = True
    calls: list[str] = field(default_factory=lambda: [])

    def verify(self, token: str, remote_ip: str | None) -> bool:
        self.calls.append(token)
        return self.ok


@dataclass
class CapturedEmail:
    sent: list[Email] = field(default_factory=lambda: [])
    fail: bool = False

    def send(self, email: Email) -> None:
        if self.fail:
            raise ConnectionError("smtp down")
        self.sent.append(email)

    def link_for(self, address: str) -> str:
        email = next(e for e in reversed(self.sent) if e.to == address)
        match = re.search(r"https?://\S+", email.text)
        assert match, email.text
        return match.group(0)


@dataclass
class FakeGoogle:
    identity: GoogleIdentity | None
    seen_nonce: list[str] = field(default_factory=lambda: [])

    def authorization_url(
        self, *, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str:
        return f"https://accounts.example.test/auth?state={state}"

    def identify(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> GoogleIdentity | None:
        self.seen_nonce.append(nonce)
        return self.identity if code == "good-code" else None


@pytest.fixture
def turnstile() -> FakeTurnstile:
    return FakeTurnstile()


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> CapturedEmail:
    captured = CapturedEmail()
    monkeypatch.setattr(handlers, "get_email_sender", lambda: captured)
    return captured


@pytest.fixture
def client(db: Databases, turnstile: FakeTurnstile) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_turnstile] = lambda: turnstile
    with TestClient(app) as test_client:
        yield test_client


def unique_email() -> str:
    return f"user-{uuid4().hex[:10]}@example.test"


def request_link(client: TestClient, email: str, next_path: str | None = "/app") -> None:
    response = client.post(
        "/v1/auth/magic-link",
        json={"email": email, "turnstile_token": "token", "next": next_path},
    )
    assert response.status_code == 202, response.text


def token_from(link: str) -> str:
    return link.split("token=", 1)[1]


# --- magic link ----------------------------------------------------------------------------


def test_magic_link_signs_in_through_the_outbox(
    client: TestClient, mailbox: CapturedEmail, db: Databases
) -> None:
    email = unique_email()
    request_link(client, email)

    assert mailbox.sent == []  # nothing is sent during the request
    process_pending()
    link = mailbox.link_for(email)
    assert link.startswith(f"{get_settings().web_origin}/auth/verify?token=")

    response = client.post("/v1/auth/magic-link/verify", json={"token": token_from(link)})
    assert response.status_code == 200
    assert response.json() == {"next": "/app"}
    set_cookie = response.headers["set-cookie"]
    assert SESSION_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    me = client.get("/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == email
    assert me.json()["memberships"] == []


def test_link_works_once(client: TestClient, mailbox: CapturedEmail) -> None:
    email = unique_email()
    request_link(client, email)
    process_pending()
    token = token_from(mailbox.link_for(email))

    assert client.post("/v1/auth/magic-link/verify", json={"token": token}).status_code == 200
    second = client.post("/v1/auth/magic-link/verify", json={"token": token})
    assert second.status_code == 400


def test_expired_link_is_refused(client: TestClient, mailbox: CapturedEmail, db: Databases) -> None:
    email = unique_email()
    request_link(client, email)
    process_pending()
    with db.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE login_tokens SET expires_at = now() - interval '1 second' WHERE email = :e"
            ),
            {"e": email},
        )
    response = client.post(
        "/v1/auth/magic-link/verify", json={"token": token_from(mailbox.link_for(email))}
    )
    assert response.status_code == 400


def test_sent_link_is_scrubbed_from_the_outbox(
    client: TestClient, mailbox: CapturedEmail, db: Databases
) -> None:
    email = unique_email()
    request_link(client, email)
    process_pending()
    with db.owner.connect() as conn:
        payload = conn.execute(
            text(
                "SELECT payload FROM outbox"
                " WHERE payload->>'email' = :e AND processed_at IS NOT NULL"
            ),
            {"e": email},
        ).scalar_one()
    assert "url" not in payload


def test_only_token_hashes_are_stored(
    client: TestClient, mailbox: CapturedEmail, db: Databases
) -> None:
    email = unique_email()
    request_link(client, email)
    process_pending()
    token = token_from(mailbox.link_for(email))
    with db.owner.connect() as conn:
        stored = conn.execute(
            text("SELECT token_hash FROM login_tokens WHERE email = :e"), {"e": email}
        ).scalar_one()
    assert token.encode() not in bytes(stored)
    assert len(bytes(stored)) == 32


def test_failed_turnstile_sends_nothing(
    client: TestClient, turnstile: FakeTurnstile, mailbox: CapturedEmail, db: Databases
) -> None:
    turnstile.ok = False
    email = unique_email()
    response = client.post("/v1/auth/magic-link", json={"email": email, "turnstile_token": "bad"})
    assert response.status_code == 400
    with db.owner.connect() as conn:
        stored = conn.execute(
            text("SELECT count(*) FROM login_tokens WHERE email = :e"), {"e": email}
        ).scalar_one()
    assert stored == 0


def test_requests_are_rate_limited_per_address(
    client: TestClient, mailbox: CapturedEmail, db: Databases
) -> None:
    email = unique_email()
    limit = get_settings().magic_links_per_15_minutes
    for _ in range(limit + 2):
        request_link(client, email)  # always 202, so the limit reveals nothing
    process_pending()
    assert sum(1 for e in mailbox.sent if e.to == email) == limit


def test_next_cannot_redirect_off_site(client: TestClient, mailbox: CapturedEmail) -> None:
    email = unique_email()
    request_link(client, email, next_path="//evil.example/steal")
    process_pending()
    response = client.post(
        "/v1/auth/magic-link/verify", json={"token": token_from(mailbox.link_for(email))}
    )
    assert response.json() == {"next": "/"}


def test_failed_email_is_retried_later(
    client: TestClient, mailbox: CapturedEmail, db: Databases
) -> None:
    email = unique_email()
    mailbox.fail = True
    request_link(client, email)
    process_pending()
    with db.owner.connect() as conn:
        row = conn.execute(
            text(
                "SELECT attempts, last_error, processed_at, available_at > now() AS deferred"
                " FROM outbox WHERE payload->>'email' = :e"
            ),
            {"e": email},
        ).one()
    assert (row.attempts, row.processed_at, row.deferred) == (1, None, True)
    assert "smtp down" in row.last_error


# --- sessions ------------------------------------------------------------------------------


def test_me_requires_a_session(client: TestClient) -> None:
    assert client.get("/v1/me").status_code == 401


def test_sign_out_ends_the_session(client: TestClient, mailbox: CapturedEmail) -> None:
    email = unique_email()
    request_link(client, email)
    process_pending()
    client.post("/v1/auth/magic-link/verify", json={"token": token_from(mailbox.link_for(email))})
    token = client.cookies.get(SESSION_COOKIE)
    assert token

    assert client.post("/v1/auth/signout").status_code == 204
    client.cookies.set(SESSION_COOKIE, token)  # replaying the old cookie does not work
    assert client.get("/v1/me").status_code == 401


def test_cross_origin_writes_are_refused(client: TestClient) -> None:
    response = client.post("/v1/auth/signout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    same_origin = client.post("/v1/auth/signout", headers={"Origin": get_settings().web_origin})
    assert same_origin.status_code == 204


# --- owner portal access (P1-03 acceptance) ------------------------------------------------


def sign_in_as(client: TestClient, user_email: str) -> None:
    signed_in = service.sign_in_verified_email(user_email, None, "/app", "pytest")
    client.cookies.set(SESSION_COOKIE, signed_in.session_token)


def test_owner_reaches_own_portal_but_not_another_tenants(
    client: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    sign_in_as(client, "owner@alpha.test")

    own = client.get(f"/v1/tenants/{alpha.tenant_id}")
    assert own.status_code == 200
    assert own.json() == {
        "id": str(alpha.tenant_id),
        "name": "alpha",
        "role": "owner",
        "financing_demo": False,
    }

    assert client.get(f"/v1/tenants/{bravo.tenant_id}").status_code == 404
    memberships = client.get("/v1/me").json()["memberships"]
    assert [m["tenant_id"] for m in memberships] == [str(alpha.tenant_id)]


def test_buyer_reaches_no_portal(
    client: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    sign_in_as(client, "buyer@alpha.test")
    assert client.get(f"/v1/tenants/{alpha.tenant_id}").status_code == 404


def test_portal_needs_a_session(client: TestClient, tenants: tuple[TenantData, TenantData]) -> None:
    alpha, _ = tenants
    assert client.get(f"/v1/tenants/{alpha.tenant_id}").status_code == 401


# --- Google --------------------------------------------------------------------------------


def test_google_is_dormant_without_credentials(client: TestClient) -> None:
    assert client.get("/v1/auth/providers").json()["google"] is False
    start = client.get("/v1/auth/google/start", follow_redirects=False)
    assert start.status_code == 404


def test_google_sign_in(db: Databases, turnstile: FakeTurnstile) -> None:
    email = unique_email()
    google = FakeGoogle(identity=GoogleIdentity(email=email, name="Pat Example"))
    app = create_app()
    app.dependency_overrides[get_google] = lambda: google
    with TestClient(app) as client:
        assert client.get("/v1/auth/providers").json()["google"] is True

        start = client.get("/v1/auth/google/start?next=/app", follow_redirects=False)
        assert start.status_code == 302
        state = start.headers["location"].split("state=", 1)[1]

        wrong = client.get(
            f"/v1/auth/google/callback?code=good-code&state=not-{state}", follow_redirects=False
        )
        assert wrong.headers["location"] == "/signin?error=google"

        start = client.get("/v1/auth/google/start?next=/app", follow_redirects=False)
        state = start.headers["location"].split("state=", 1)[1]
        done = client.get(
            f"/v1/auth/google/callback?code=good-code&state={state}", follow_redirects=False
        )
        assert done.status_code == 303
        assert done.headers["location"] == "/app"
        me = client.get("/v1/me").json()
        assert (me["email"], me["display_name"]) == (email, "Pat Example")
