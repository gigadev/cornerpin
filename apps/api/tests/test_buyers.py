"""P1-08: buyer activity. An inquiry reaches the owner; consent rows carry channel and
timestamp; saving and holding work only on lots the public can see."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.core.auth.turnstile import get_turnstile
from cornerpin.main import create_app

from .conftest import Databases, TenantData

Json = dict[str, Any]
# Any token passes the fake verifier unless a test says otherwise.
TURNSTILE: Json = {"turnstile_token": "t"}


@dataclass
class FakeTurnstile:
    ok: bool = True
    calls: list[str] = field(default_factory=lambda: [])

    def verify(self, token: str, remote_ip: str | None) -> bool:
        self.calls.append(token)
        return self.ok


@dataclass(frozen=True)
class Listing:
    tenant: TenantData
    subdivision_id: str
    available: str
    sold: str
    unpublished: str


@pytest.fixture
def turnstile() -> FakeTurnstile:
    return FakeTurnstile()


@pytest.fixture
def client_for(
    db: Databases, turnstile: FakeTurnstile
) -> Iterator[Callable[[str | None], TestClient]]:
    """Clients signed in as the given email (created on first use), or anonymous for None."""
    clients: list[TestClient] = []

    def make(email: str | None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_turnstile] = lambda: turnstile
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        if email:
            signed_in = service.sign_in_verified_email(email, None, "/", "pytest")
            client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def buyer(client_for: Callable[[str | None], TestClient]) -> TestClient:
    return client_for(f"buyer-{uuid4().hex[:10]}@example.test")


@pytest.fixture
def anonymous(client_for: Callable[[str | None], TestClient]) -> TestClient:
    return client_for(None)


@pytest.fixture
def listing(alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]) -> Listing:
    alpha, _ = tenants
    base = f"/v1/tenants/{alpha.tenant_id}"
    subdivision = alpha_owner.post(
        f"{base}/subdivisions",
        json={"name": "Buyers", "slug": f"buyers-{uuid4().hex[:8]}", "time_zone": "America/Boise",
              "latitude": 43.6, "longitude": -116.2, "published": True},
    ).json()  # fmt: skip
    phase = alpha_owner.post(
        f"{base}/subdivisions/{subdivision['id']}/phases", json={"name": "Phase 1"}
    ).json()

    def lot(number: str, **fields: Any) -> str:
        created = alpha_owner.post(
            f"{base}/subdivisions/{subdivision['id']}/lots",
            json={"number": number, "phase_id": phase["id"], "price": 90000, **fields},
        )
        assert created.status_code == 201, created.text
        lot_id: str = created.json()["id"]
        return lot_id

    return Listing(
        tenant=alpha,
        subdivision_id=subdivision["id"],
        available=lot("1", published=True),
        sold=lot("2", published=True, status="sold"),
        unpublished=lot("3"),
    )


def inquiry(**fields: Any) -> Json:
    return {"name": "Pat Buyer", "message": "Is the well shared?", **fields}


def consent_rows(db: Databases, lot: Listing, email: str) -> list[Any]:
    with db.owner.connect() as conn:
        return list(
            conn.execute(
                text(
                    "SELECT c.channel::text AS channel, c.granted, c.source, c.recorded_at"
                    " FROM contact_consents c JOIN users u ON u.id = c.user_id"
                    " WHERE u.email = :email AND c.tenant_id = :t ORDER BY c.recorded_at"
                ),
                {"email": email, "t": lot.tenant.tenant_id},
            )
        )


def owner_inquiries(owner: TestClient, lot: Listing) -> list[Json]:
    response = owner.get(f"/v1/tenants/{lot.tenant.tenant_id}/inquiries")
    assert response.status_code == 200, response.text
    rows: list[Json] = response.json()
    return rows


def me(client: TestClient) -> Json:
    body: Json = client.get("/v1/me").json()
    return body


# --- inquiries -----------------------------------------------------------------------------


def test_anonymous_inquiry_reaches_the_owner(
    anonymous: TestClient, alpha_owner: TestClient, listing: Listing, turnstile: FakeTurnstile
) -> None:
    sent = anonymous.post(
        f"/v1/lots/{listing.available}/inquiries",
        json=inquiry(email="Walk.In@Example.test", phone="(208) 555-0142", **TURNSTILE),
    )
    assert sent.status_code == 201, sent.text
    assert turnstile.calls == ["t"]

    found = [i for i in owner_inquiries(alpha_owner, listing) if i["id"] == sent.json()["id"]]
    assert len(found) == 1
    assert found[0] | {"id": None, "created_at": None, "lot_id": None} == {
        "id": None,
        "lot_id": None,
        "lot_number": "1",
        "subdivision_name": "Buyers",
        "name": "Pat Buyer",
        "email": "Walk.In@example.test",
        "phone": "+12085550142",
        "message": "Is the well shared?",
        "signed_in": False,
        "contact": [],
        "created_at": None,
    }


@pytest.mark.parametrize(
    ("fields", "turnstile_ok", "expected"),
    [
        ({"email": "a@example.test", "turnstile_token": "t"}, False, 400),
        ({"turnstile_token": "t"}, True, 422),
        (
            {"email": "a@example.test", "turnstile_token": "t", "contact": {"email": True}},
            True,
            422,
        ),
        ({"email": "a@example.test", "turnstile_token": "t", "message": " "}, True, 422),
        ({"email": "a@example.test", "turnstile_token": "t", "phone": "12"}, True, 422),
    ],
)
def test_anonymous_inquiry_is_checked(
    anonymous: TestClient,
    listing: Listing,
    turnstile: FakeTurnstile,
    db: Databases,
    fields: Json,
    turnstile_ok: bool,
    expected: int,
) -> None:
    turnstile.ok = turnstile_ok
    response = anonymous.post(f"/v1/lots/{listing.available}/inquiries", json=inquiry(**fields))
    assert response.status_code == expected, response.text
    with db.owner.connect() as conn:
        stored = conn.execute(
            text("SELECT count(*) FROM inquiries WHERE lot_id = :l"), {"l": listing.available}
        ).scalar_one()
    assert stored == 0


def test_unpublished_lots_take_no_buyer_activity(
    anonymous: TestClient, buyer: TestClient, listing: Listing
) -> None:
    lot = listing.unpublished
    anonymous_inquiry = anonymous.post(
        f"/v1/lots/{lot}/inquiries", json=inquiry(email="a@example.test", **TURNSTILE)
    )
    assert anonymous_inquiry.status_code == 404
    assert buyer.post(f"/v1/lots/{lot}/inquiries", json=inquiry()).status_code == 404
    assert buyer.post(f"/v1/lots/{lot}/hold-requests", json={"name": "Pat"}).status_code == 404
    assert buyer.put(f"/v1/me/saved-lots/{lot}").status_code == 404
    assert buyer.get(f"/v1/me/lots/{lot}").status_code == 404
    assert buyer.put(f"/v1/me/saved-lots/{uuid4()}").status_code == 404


def test_signed_in_inquiry_records_consent_with_channel_and_timestamp(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    email = me(buyer)["email"]
    before = datetime.now().astimezone()
    sent = buyer.post(
        f"/v1/lots/{listing.available}/inquiries",
        json=inquiry(
            email="someone-else@example.test",  # ignored: the account's address is used
            phone="208.555.0199",
            contact={"email": True, "sms": True},
        ),
    )
    assert sent.status_code == 201, sent.text

    rows = consent_rows(db, listing, email)
    assert [(r.channel, r.granted, r.source) for r in rows] == [
        ("email", True, "inquiry"),
        ("sms", True, "inquiry"),
    ]
    assert all(r.recorded_at >= before for r in rows)

    found = next(i for i in owner_inquiries(alpha_owner, listing) if i["id"] == sent.json()["id"])
    assert (found["email"], found["signed_in"], found["contact"]) == (email, True, ["email", "sms"])
    # The form filled in the empty profile.
    assert (me(buyer)["display_name"], me(buyer)["phone"]) == ("Pat Buyer", "+12085550199")


def test_consent_rows_are_added_only_for_changes(
    buyer: TestClient, listing: Listing, db: Databases
) -> None:
    email = me(buyer)["email"]
    url = f"/v1/lots/{listing.available}/inquiries"
    buyer.post(url, json=inquiry(contact={"email": True, "sms": False}))
    buyer.post(url, json=inquiry(contact={"email": True, "sms": False}))
    buyer.post(url, json=inquiry())  # no contact field: unchanged
    assert [(r.channel, r.granted) for r in consent_rows(db, listing, email)] == [("email", True)]

    buyer.post(url, json=inquiry(contact={"email": False, "sms": False}))
    assert [(r.channel, r.granted) for r in consent_rows(db, listing, email)] == [
        ("email", True),
        ("email", False),
    ]
    state = buyer.get(f"/v1/me/lots/{listing.available}").json()
    assert state["contact"] == {"email": False, "sms": False}


def test_text_messages_need_a_phone_number(
    buyer: TestClient, listing: Listing, db: Databases
) -> None:
    response = buyer.post(
        f"/v1/lots/{listing.available}/inquiries", json=inquiry(contact={"sms": True})
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Add a phone number to get text messages"
    with db.owner.connect() as conn:
        stored = conn.execute(
            text("SELECT count(*) FROM inquiries WHERE lot_id = :l"), {"l": listing.available}
        ).scalar_one()
    assert stored == 0  # the whole request rolled back


# --- saved lots ----------------------------------------------------------------------------


def test_save_and_unsave_a_lot(buyer: TestClient, listing: Listing) -> None:
    lot = listing.available
    assert buyer.put(f"/v1/me/saved-lots/{lot}").status_code == 204
    assert buyer.put(f"/v1/me/saved-lots/{lot}").status_code == 204  # idempotent
    assert buyer.get(f"/v1/me/lots/{lot}").json()["saved"] is True

    saved = buyer.get("/v1/me/saved-lots").json()
    assert [(s["lot_id"], s["number"], s["status"], s["price"], s["subdivision_name"])
            for s in saved] == [(lot, "1", "available", 90000, "Buyers")]  # fmt: skip

    assert buyer.delete(f"/v1/me/saved-lots/{lot}").status_code == 204
    assert buyer.get("/v1/me/saved-lots").json() == []
    assert buyer.get(f"/v1/me/lots/{lot}").json()["saved"] is False


def test_saved_lot_drops_out_while_unpublished(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing
) -> None:
    lot = listing.available
    buyer.put(f"/v1/me/saved-lots/{lot}")
    path = f"/v1/tenants/{listing.tenant.tenant_id}/lots/{lot}"
    alpha_owner.patch(path, json={"published": False})
    assert buyer.get("/v1/me/saved-lots").json() == []
    alpha_owner.patch(path, json={"published": True})
    assert [s["lot_id"] for s in buyer.get("/v1/me/saved-lots").json()] == [lot]


def test_buyer_endpoints_need_sign_in(anonymous: TestClient, listing: Listing) -> None:
    lot = listing.available
    assert anonymous.get(f"/v1/me/lots/{lot}").status_code == 401
    assert anonymous.put(f"/v1/me/saved-lots/{lot}").status_code == 401
    assert anonymous.get("/v1/me/saved-lots").status_code == 401
    assert anonymous.post(f"/v1/lots/{lot}/hold-requests", json={"name": "P"}).status_code == 401
    assert anonymous.get("/v1/me/consents").status_code == 401
    assert anonymous.get("/v1/me/notification-prefs").status_code == 401


# --- hold requests -------------------------------------------------------------------------


def holds(owner: TestClient, lot: Listing) -> list[Json]:
    rows: list[Json] = owner.get(f"/v1/tenants/{lot.tenant.tenant_id}/hold-requests").json()
    return rows


def decide(owner: TestClient, lot: Listing, hold_id: str, decision: str) -> Any:
    return owner.post(
        f"/v1/tenants/{lot.tenant.tenant_id}/hold-requests/{hold_id}/decision",
        json={"decision": decision},
    )


def lot_status(owner: TestClient, lot: Listing, lot_id: str) -> str:
    status: str = owner.get(f"/v1/tenants/{lot.tenant.tenant_id}/lots/{lot_id}").json()["status"]
    return status


def test_approving_a_hold_puts_the_lot_on_hold(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    lot = listing.available
    created = buyer.post(
        f"/v1/lots/{lot}/hold-requests",
        json={"name": "Pat Buyer", "message": "Back from the bank Friday",
              "contact": {"email": True}},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    hold_id = created.json()["id"]
    again = buyer.post(f"/v1/lots/{lot}/hold-requests", json={"name": "Pat Buyer"})
    assert again.status_code == 409
    assert buyer.get(f"/v1/me/lots/{lot}").json()["pending_hold"] is True

    pending = next(h for h in holds(alpha_owner, listing) if h["id"] == hold_id)
    assert (pending["status"], pending["lot_status"], pending["contact"]) == (
        "pending",
        "available",
        ["email"],
    )

    approved = decide(alpha_owner, listing, hold_id, "approve")
    assert approved.status_code == 200, approved.text
    assert (approved.json()["status"], approved.json()["lot_status"]) == ("approved", "on_hold")
    assert approved.json()["decided_at"] is not None
    assert lot_status(alpha_owner, listing, lot) == "on_hold"
    with db.owner.connect() as conn:
        history = conn.execute(
            text(
                "SELECT to_status::text, changed_by IS NOT NULL FROM lot_status_history"
                " WHERE lot_id = :l ORDER BY changed_at DESC LIMIT 1"
            ),
            {"l": lot},
        ).one()
    assert tuple(history) == ("on_hold", True)

    assert decide(alpha_owner, listing, hold_id, "decline").status_code == 409
    assert buyer.get(f"/v1/me/lots/{lot}").json()["pending_hold"] is False
    # The lot is no longer available, so nobody else can ask to hold it.
    assert buyer.post(f"/v1/lots/{lot}/hold-requests", json={"name": "P"}).status_code == 409


def test_declining_a_hold_leaves_the_lot_alone(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing
) -> None:
    hold_id = buyer.post(
        f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat"}
    ).json()["id"]
    declined = decide(alpha_owner, listing, hold_id, "decline")
    assert declined.json()["status"] == "declined"
    assert lot_status(alpha_owner, listing, listing.available) == "available"
    # A declined request no longer blocks a new one.
    again = buyer.post(f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat"})
    assert again.status_code == 201


def test_only_available_lots_can_be_held(buyer: TestClient, listing: Listing) -> None:
    response = buyer.post(f"/v1/lots/{listing.sold}/hold-requests", json={"name": "Pat"})
    assert response.status_code == 409


def test_a_sold_lot_cannot_be_approved(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing
) -> None:
    hold_id = buyer.post(
        f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat"}
    ).json()["id"]
    alpha_owner.patch(
        f"/v1/tenants/{listing.tenant.tenant_id}/lots/{listing.available}",
        json={"status": "sold"},
    )
    response = decide(alpha_owner, listing, hold_id, "approve")
    assert response.status_code == 409
    assert response.json()["detail"] == "This lot is already sold"


def test_other_tenants_and_buyers_cannot_see_or_decide(
    buyer: TestClient,
    client_for: Callable[[str | None], TestClient],
    listing: Listing,
    tenants: tuple[TenantData, TenantData],
) -> None:
    _, bravo = tenants
    hold_id = buyer.post(
        f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat"}
    ).json()["id"]
    alpha_base = f"/v1/tenants/{listing.tenant.tenant_id}"
    bravo_owner = client_for("owner@bravo.test")

    assert bravo_owner.get(f"{alpha_base}/inquiries").status_code == 404
    assert bravo_owner.get(f"{alpha_base}/hold-requests").status_code == 404
    via_bravo = bravo_owner.post(
        f"/v1/tenants/{bravo.tenant_id}/hold-requests/{hold_id}/decision",
        json={"decision": "approve"},
    )
    assert via_bravo.status_code == 404
    assert buyer.get(f"{alpha_base}/hold-requests").status_code == 404
    mine = buyer.post(
        f"{alpha_base}/hold-requests/{hold_id}/decision", json={"decision": "approve"}
    )
    assert mine.status_code == 404


# --- account -------------------------------------------------------------------------------


def test_profile_changes(buyer: TestClient) -> None:
    changed = buyer.patch(
        "/v1/me",
        json={"display_name": " Pat ", "phone": "+44 20 7946 0958", "time_zone": "America/Boise"},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["display_name"], body["phone"], body["time_zone"]) == (
        "Pat",
        "+442079460958",
        "America/Boise",
    )
    assert buyer.patch("/v1/me", json={"phone": "555"}).status_code == 422
    assert buyer.patch("/v1/me", json={"time_zone": "Mars/Base"}).status_code == 422
    cleared = buyer.patch("/v1/me", json={"display_name": "", "phone": None}).json()
    assert (cleared["display_name"], cleared["phone"], cleared["time_zone"]) == (
        None,
        None,
        "America/Boise",
    )


def test_notification_preferences(buyer: TestClient) -> None:
    assert buyer.get("/v1/me/notification-prefs").json() == {
        "email_saved_lot_changes": True,
        "push_saved_lot_changes": False,
    }
    off = {"email_saved_lot_changes": False, "push_saved_lot_changes": False}
    assert buyer.put("/v1/me/notification-prefs", json=off).json() == off
    assert buyer.get("/v1/me/notification-prefs").json() == off


def test_consent_can_be_changed_from_the_account_page(
    buyer: TestClient, listing: Listing, db: Databases
) -> None:
    email = me(buyer)["email"]
    buyer.post(f"/v1/lots/{listing.available}/inquiries", json=inquiry(contact={"email": True}))
    consents = buyer.get("/v1/me/consents").json()
    assert [(c["tenant_name"], c["channel"], c["granted"], c["source"]) for c in consents] == [
        ("alpha", "email", True, "inquiry")
    ]

    tenant_id = str(listing.tenant.tenant_id)
    withdrawn = buyer.post(
        "/v1/me/consents", json={"tenant_id": tenant_id, "channel": "email", "granted": False}
    )
    assert withdrawn.status_code == 204
    texts = buyer.post(
        "/v1/me/consents", json={"tenant_id": tenant_id, "channel": "sms", "granted": True}
    )
    assert texts.status_code == 422  # no phone on the profile
    assert [(r.channel, r.granted, r.source) for r in consent_rows(db, listing, email)] == [
        ("email", True, "inquiry"),
        ("email", False, "account"),
    ]

    unknown = buyer.post(
        "/v1/me/consents", json={"tenant_id": str(uuid4()), "channel": "email", "granted": True}
    )
    assert unknown.status_code == 404
