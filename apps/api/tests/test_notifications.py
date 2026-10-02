"""P1-09: notifications. A status change produces exactly one email per saver; owners hear
about inquiries and hold requests; web push for devices that ask for it."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from py_vapid import Vapid02  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import text

from cornerpin.core import internal
from cornerpin.core.db import user_session
from cornerpin.core.housekeeping import run_housekeeping
from cornerpin.core.outbox import drain, enqueue, set_dispatcher
from cornerpin.devtools import vapid_keys
from cornerpin.listings.events import LotChanged
from cornerpin.listings.models import LotStatus
from cornerpin.listings.notices import LotNotice
from cornerpin.main import create_app
from cornerpin.notifications import handlers, messages
from cornerpin.notifications.email import Email
from cornerpin.notifications.events import SavedLotEmail
from cornerpin.notifications.push import PushGone, PushTarget

from .conftest import Databases, Listing, TenantData

Json = dict[str, Any]
FCM = "https://fcm.googleapis.com/fcm/send/"


@dataclass
class Mailbox:
    sent: list[Email] = field(default_factory=lambda: [])
    failing: set[str] = field(default_factory=lambda: set())

    def send(self, email: Email) -> None:
        if email.to in self.failing:
            raise ConnectionError(f"cannot reach {email.to}")
        self.sent.append(email)

    def to(self, address: str) -> list[Email]:
        return [email for email in self.sent if email.to == address]


@dataclass
class FakePush:
    sent: list[tuple[str, Mapping[str, str]]] = field(default_factory=lambda: [])
    gone: set[str] = field(default_factory=lambda: set())

    def send(self, target: PushTarget, message: Mapping[str, str]) -> None:
        if target.endpoint in self.gone:
            raise PushGone("410 Gone")
        self.sent.append((target.endpoint, message))


@pytest.fixture
def mailbox(db: Databases, monkeypatch: pytest.MonkeyPatch) -> Mailbox:
    box = Mailbox()
    monkeypatch.setattr(handlers, "get_email_sender", lambda: box)
    drain()  # start from an empty outbox; earlier tests leave events behind
    box.sent.clear()
    return box


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch) -> FakePush:
    fake = FakePush()
    monkeypatch.setattr(handlers, "get_push_sender", lambda: fake)
    return fake


def new_email() -> str:
    return f"saver-{uuid4().hex[:10]}@example.test"


def owner_patch(owner: TestClient, listing: Listing, lot_id: str, **fields: Any) -> None:
    response = owner.patch(f"/v1/tenants/{listing.tenant.tenant_id}/lots/{lot_id}", json=fields)
    assert response.status_code == 200, response.text


def make_overdue(db: Databases) -> None:
    """Skip the retry back-off."""
    with db.owner.begin() as conn:
        conn.execute(text("UPDATE outbox SET available_at = now() WHERE processed_at IS NULL"))


# --- savers --------------------------------------------------------------------------------


def test_a_status_change_emails_each_saver_exactly_once(
    client_for: Callable[[str | None], TestClient],
    alpha_owner: TestClient,
    listing: Listing,
    mailbox: Mailbox,
) -> None:
    savers = [new_email(), new_email()]
    quiet = new_email()
    for email in [*savers, quiet]:
        client = client_for(email)
        assert client.put(f"/v1/me/saved-lots/{listing.available}").status_code == 204
        if email == quiet:
            client.put(
                "/v1/me/notification-prefs",
                json={"email_saved_lot_changes": False, "push_saved_lot_changes": False},
            )
    stranger = new_email()
    client_for(stranger)

    owner_patch(alpha_owner, listing, listing.available, status="on_hold")
    drain()
    drain()  # nothing left to send twice

    for email in savers:
        sent = mailbox.to(email)
        assert len(sent) == 1
        assert sent[0].subject == "Lot 1 at Buyers is now on hold"
        assert "Status: available → on hold" in sent[0].text
        assert "/lots/1" in sent[0].text
        assert "/account" in sent[0].text
    assert mailbox.to(quiet) == []
    assert mailbox.to(stranger) == []


def test_price_and_status_in_one_change_make_one_email(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, mailbox: Mailbox
) -> None:
    email = buyer.get("/v1/me").json()["email"]
    buyer.put(f"/v1/me/saved-lots/{listing.available}")

    owner_patch(alpha_owner, listing, listing.available, status="sold", price=85000)
    owner_patch(alpha_owner, listing, listing.available, acreage=1.5)  # neither: no email
    drain()

    sent = mailbox.to(email)
    assert [e.subject for e in sent] == ["Lot 1 at Buyers is now sold, $85,000 (was $90,000)"]
    assert "Price: $90,000 → $85,000" in sent[0].text


def test_no_email_about_a_lot_the_public_cannot_see(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, mailbox: Mailbox
) -> None:
    email = buyer.get("/v1/me").json()["email"]
    buyer.put(f"/v1/me/saved-lots/{listing.available}")
    owner_patch(alpha_owner, listing, listing.available, published=False, status="sold")
    drain()
    assert mailbox.to(email) == []


def test_a_failed_send_retries_for_that_saver_alone(
    client_for: Callable[[str | None], TestClient],
    alpha_owner: TestClient,
    listing: Listing,
    mailbox: Mailbox,
    db: Databases,
) -> None:
    working, failing = new_email(), new_email()
    for email in (working, failing):
        client_for(email).put(f"/v1/me/saved-lots/{listing.available}")
    mailbox.failing.add(failing)

    owner_patch(alpha_owner, listing, listing.available, status="on_hold")
    drain()
    assert (len(mailbox.to(working)), len(mailbox.to(failing))) == (1, 0)

    mailbox.failing.clear()
    make_overdue(db)
    drain()
    assert (len(mailbox.to(working)), len(mailbox.to(failing))) == (1, 1)


# --- owners --------------------------------------------------------------------------------


def test_an_inquiry_emails_the_owners(
    anonymous: TestClient, listing: Listing, mailbox: Mailbox
) -> None:
    sent = anonymous.post(
        f"/v1/lots/{listing.available}/inquiries",
        json={"name": "Walk-in", "email": "walkin@example.test", "phone": "208-555-0142",
              "message": "Is the well shared?", "turnstile_token": "t"},
    )  # fmt: skip
    assert sent.status_code == 201
    drain()

    [email] = mailbox.to("owner@alpha.test")
    assert email.subject == "New question about Lot 1 at Buyers"
    assert email.reply_to == "walkin@example.test"
    assert "Walk-in (walkin@example.test, +12085550142) asked about Lot 1 at Buyers." in email.text
    assert "Is the well shared?" in email.text
    assert "hasn't been verified" in email.text
    assert f"/app/{listing.tenant.tenant_id}/inquiries" in email.text


def test_a_hold_request_emails_the_owners(
    buyer: TestClient, listing: Listing, mailbox: Mailbox
) -> None:
    buyer_email = buyer.get("/v1/me").json()["email"]
    created = buyer.post(
        f"/v1/lots/{listing.available}/hold-requests",
        json={"name": "Pat", "message": "Back Friday"},
    )
    assert created.status_code == 201
    drain()

    [email] = mailbox.to("owner@alpha.test")
    assert email.subject == "Hold request for Lot 1 at Buyers"
    assert email.reply_to == buyer_email
    assert "Approve or decline" in email.text
    assert "verified" not in email.text


def test_outbox_payloads_hold_ids_not_messages(
    anonymous: TestClient, listing: Listing, db: Databases
) -> None:
    anonymous.post(
        f"/v1/lots/{listing.available}/inquiries",
        json={"name": "Walk-in", "email": "private@example.test", "message": "My budget is...",
              "turnstile_token": "t"},
    )  # fmt: skip
    with db.owner.connect() as conn:
        payloads = conn.execute(
            text("SELECT payload::text FROM outbox WHERE event_type LIKE 'leads.%'")
        ).scalars()
        assert not any("private@example.test" in p or "budget" in p for p in payloads)


# --- web push ------------------------------------------------------------------------------


def test_push_goes_to_devices_that_asked_and_dead_ones_are_removed(
    buyer: TestClient,
    alpha_owner: TestClient,
    listing: Listing,
    mailbox: Mailbox,
    push: FakePush,
    db: Databases,
) -> None:
    phone, old_laptop = f"{FCM}{uuid4().hex}", f"{FCM}{uuid4().hex}"
    for endpoint in (phone, old_laptop):
        added = buyer.put(
            "/v1/me/push-subscriptions",
            json={"endpoint": endpoint, "keys": {"p256dh": "BPublicKey123", "auth": "authSecret"}},
        )
        assert added.status_code == 204, added.text
    buyer.put(
        "/v1/me/notification-prefs",
        json={"email_saved_lot_changes": False, "push_saved_lot_changes": True},
    )
    buyer.put(f"/v1/me/saved-lots/{listing.available}")
    push.gone.add(old_laptop)

    owner_patch(alpha_owner, listing, listing.available, price=88000)
    drain()

    assert [(endpoint, message["title"], message["body"]) for endpoint, message in push.sent] == [
        (phone, "Lot 1 · Buyers", "Is now $88,000 (was $90,000)")
    ]
    assert push.sent[0][1]["url"].endswith("/lots/1")
    with db.owner.connect() as conn:
        left = conn.execute(
            text("SELECT endpoint FROM push_subscriptions WHERE endpoint IN (:a, :b)"),
            {"a": phone, "b": old_laptop},
        ).scalars()
        assert list(left) == [phone]


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/x",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com.evil.test/x",
        "https://localhost/push",
    ],
)
def test_push_endpoints_must_be_browser_push_services(buyer: TestClient, endpoint: str) -> None:
    response = buyer.put(
        "/v1/me/push-subscriptions",
        json={"endpoint": endpoint, "keys": {"p256dh": "BPublicKey123", "auth": "authSecret"}},
    )
    assert response.status_code == 422


def test_push_is_off_without_keys(anonymous: TestClient) -> None:
    assert anonymous.get("/v1/push/config").json() == {"public_key": None}


def test_generated_vapid_keys_sign_a_push_claim() -> None:
    public, private = vapid_keys()
    vapid = Vapid02.from_string(private)  # pyright: ignore[reportUnknownMemberType]
    headers: Json = vapid.sign(  # pyright: ignore[reportUnknownMemberType]
        {"aud": "https://fcm.googleapis.com", "sub": "mailto:hello@cornerpin.app"}
    )
    assert public in str(headers["Authorization"])


# --- messages ------------------------------------------------------------------------------


LOT = LotNotice(
    id=uuid4(),
    tenant_id=uuid4(),
    number="7",
    status=LotStatus.AVAILABLE,
    price=None,
    subdivision_name="Juniper Bench",
    subdivision_slug="juniper-bench",
    public=True,
)


def change(**fields: Any) -> LotChanged:
    base: Json = {
        "lot_id": LOT.id,
        "from_status": "available",
        "to_status": "available",
        "from_price": Decimal("549000.00"),
        "to_price": Decimal("549000.00"),
    }
    return LotChanged.model_validate(base | fields)


@pytest.mark.parametrize(
    ("fields", "summary"),
    [
        ({"to_status": "on_hold"}, "Lot 7 at Juniper Bench is now on hold"),
        ({"to_price": Decimal("529000")}, "Lot 7 at Juniper Bench is now $529,000 (was $549,000)"),
        ({"to_price": None}, "Lot 7 at Juniper Bench is now no price (was $549,000)"),
        (
            {"to_status": "sold", "to_price": Decimal("530000")},
            "Lot 7 at Juniper Bench is now sold, $530,000 (was $549,000)",
        ),
    ],
)
def test_lot_change_summaries(fields: Json, summary: str) -> None:
    assert messages.lot_change_summary(LOT, change(**fields)) == summary


# --- the trigger, dispatch and the cloud endpoints -----------------------------------------


def test_only_status_and_price_changes_queue_an_event(
    alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    def queued() -> int:
        with db.owner.connect() as conn:
            count: int = conn.execute(
                text(
                    "SELECT count(*) FROM outbox WHERE event_type = 'listings.lot_changed'"
                    " AND payload->>'lot_id' = :id"
                ),
                {"id": listing.available},
            ).scalar_one()
            return count

    owner_patch(alpha_owner, listing, listing.available, acreage=2.0)
    assert queued() == 0
    owner_patch(alpha_owner, listing, listing.available, status="sold")
    assert queued() == 1


@dataclass
class CountingDispatcher:
    calls: int = 0

    def notify(self) -> None:
        self.calls += 1


@pytest.fixture
def dispatcher() -> Iterator[CountingDispatcher]:
    counting = CountingDispatcher()
    set_dispatcher(counting)
    yield counting
    set_dispatcher(None)


def test_dispatcher_is_told_after_commit_not_after_rollback(
    dispatcher: CountingDispatcher, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    event = SavedLotEmail.model_validate(
        {"user_id": alpha.buyer_id, "change": change().model_dump()}
    )
    with pytest.raises(RuntimeError), user_session(alpha.buyer_id) as session:
        enqueue(session, event)
        raise RuntimeError("abandon")
    assert dispatcher.calls == 0
    with user_session(alpha.buyer_id) as session:
        enqueue(session, event)
    assert dispatcher.calls == 1


def test_cloud_tasks_dispatcher_creates_an_authenticated_task() -> None:
    posted: list[tuple[str, Json]] = []
    tasks = internal.CloudTasksDispatcher(
        queue="projects/p/locations/us-west1/queues/outbox",
        base_url="https://api.example.test",
        service_account="tasks@p.iam.gserviceaccount.com",
        post=lambda url, body: posted.append((url, body)),
    )
    tasks.notify()
    assert posted == [
        (
            "https://cloudtasks.googleapis.com/v2/projects/p/locations/us-west1/queues/outbox/tasks",
            {
                "task": {
                    "httpRequest": {
                        "httpMethod": "POST",
                        "url": "https://api.example.test/internal/outbox/drain",
                        "oidcToken": {
                            "serviceAccountEmail": "tasks@p.iam.gserviceaccount.com",
                            "audience": "https://api.example.test",
                        },
                    }
                }
            },
        )
    ]


GOOD_TOKEN = "good"  # noqa: S105 -- what the fake verifier accepts


class TokenVerifier:
    def verify(self, token: str) -> bool:
        return token == GOOD_TOKEN


def test_internal_endpoints_are_off_locally(db: Databases) -> None:
    with TestClient(create_app()) as client:
        assert client.post("/internal/outbox/drain").status_code == 404
        assert client.post("/internal/housekeeping").status_code == 404


def test_internal_endpoints_need_the_tasks_token(db: Databases, mailbox: Mailbox) -> None:
    app = create_app()
    app.dependency_overrides[internal.get_task_verifier] = TokenVerifier
    with TestClient(app) as client:
        assert client.post("/internal/outbox/drain").status_code == 403
        bad = client.post("/internal/outbox/drain", headers={"Authorization": "Bearer bad"})
        assert bad.status_code == 403
        good = client.post("/internal/outbox/drain", headers={"Authorization": "Bearer good"})
        assert good.status_code == 200
        assert good.json() == {"processed": 0}
        kept = client.post("/internal/housekeeping", headers={"Authorization": "Bearer good"})
        assert kept.status_code == 200
        assert set(kept.json()) == {"login_tokens", "sessions", "outbox_events"}


def test_housekeeping_removes_only_what_has_expired(db: Databases) -> None:
    with db.owner.begin() as conn:
        for days, label in ((-3, "old"), (1, "fresh")):
            conn.execute(
                text(
                    "INSERT INTO login_tokens (token_hash, email, expires_at)"
                    " VALUES (CAST(:hash AS bytea), :email, now() + make_interval(days => :d))"
                ),
                {"hash": uuid4().bytes, "email": f"{label}@housekeeping.test", "d": days},
            )
        conn.execute(
            text(
                "INSERT INTO outbox (event_type, payload, processed_at) VALUES"
                " ('test.old', '{}', now() - interval '40 days'),"
                " ('test.recent', '{}', now() - interval '2 days')"
            )
        )

    run_housekeeping()

    with db.owner.connect() as conn:
        emails = set(
            conn.execute(
                text("SELECT email FROM login_tokens WHERE email LIKE '%@housekeeping.test'")
            ).scalars()
        )
        events = set(
            conn.execute(
                text("SELECT event_type FROM outbox WHERE event_type LIKE 'test.%'")
            ).scalars()
        )
    assert emails == {"fresh@housekeeping.test"}
    assert events == {"test.recent"}
