"""P2-01: leads (ADR-035). A buyer's inquiries, holds and consent changes become one lead per
owner, with a timeline, written in the same transaction. Owners read them and add notes and
stage changes; buyers and other tenants see nothing."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from cornerpin.core.db import user_session

from .conftest import Databases, Listing

Json = dict[str, Any]
TURNSTILE: Json = {"turnstile_token": "t"}


def email_of(client: TestClient) -> str:
    email: str = client.get("/v1/me").json()["email"]
    return email


def lead_for(db: Databases, lot: Listing, email: str) -> Any:
    """The lead as the tenant's owner sees it, through row-level security."""
    with user_session(lot.tenant.owner_id, lot.tenant.tenant_id, engine=db.api) as session:
        return session.execute(
            text(
                "SELECT id, user_id, stage::text AS stage, source, name, phone FROM leads"
                " WHERE email = :email"
            ),
            {"email": email},
        ).one_or_none()


def timeline(db: Databases, lot: Listing, lead_id: object) -> list[Any]:
    with user_session(lot.tenant.owner_id, lot.tenant.tenant_id, engine=db.api) as session:
        return list(
            session.execute(
                text(
                    "SELECT kind::text AS kind, verified, actor_user_id, detail FROM lead_events"
                    " WHERE lead_id = :lead ORDER BY created_at, kind::text"
                ),
                {"lead": lead_id},
            )
        )


def test_a_consented_inquiry_becomes_a_lead_with_its_timeline(
    buyer: TestClient, listing: Listing, db: Databases
) -> None:
    sent = buyer.post(
        f"/v1/lots/{listing.available}/inquiries",
        json={"name": "Pat Buyer", "phone": "208-555-0142", "message": "Is the well shared?",
              "contact": {"email": True}},
    )  # fmt: skip
    assert sent.status_code == 201, sent.text

    email = email_of(buyer)
    lead = lead_for(db, listing, email)
    assert lead is not None
    assert (lead.stage, lead.source, lead.name, lead.phone) == (
        "new",
        "inquiry",
        "Pat Buyer",
        "+12085550142",
    )
    assert lead.user_id is not None
    events = {e.kind: e for e in timeline(db, listing, lead.id)}
    assert set(events) == {"inquiry", "consent_changed"}
    assert events["inquiry"].verified
    assert events["inquiry"].detail == {"message": "Is the well shared?"}
    assert events["consent_changed"].detail == {
        "channel": "email",
        "granted": True,
        "source": "inquiry",
    }

    # A second inquiry is the same lead, not a new one.
    again = buyer.post(
        f"/v1/lots/{listing.available}/inquiries", json={"name": "Pat", "message": "And power?"}
    )
    assert again.status_code == 201, again.text
    assert lead_for(db, listing, email).id == lead.id
    assert [e.kind for e in timeline(db, listing, lead.id)].count("inquiry") == 2

    # The buyer can't read it, even their own.
    with user_session(lead.user_id, engine=db.api) as session:
        assert session.execute(text("SELECT count(*) FROM leads")).scalar_one() == 0


def test_an_anonymous_inquiry_joins_the_lead_unverified_and_never_attaches_a_user(
    anonymous: TestClient, buyer: TestClient, listing: Listing, db: Databases
) -> None:
    email = email_of(buyer)  # someone else could type this address
    sent = anonymous.post(
        f"/v1/lots/{listing.available}/inquiries",
        json={"name": "Someone", "email": email, "message": "Hi", **TURNSTILE},
    )
    assert sent.status_code == 201, sent.text
    lead = lead_for(db, listing, email)
    assert (lead.user_id, lead.source) == (None, "inquiry")

    # The address's real owner signs in and asks: the same lead becomes theirs.
    signed_in = buyer.post(
        f"/v1/lots/{listing.available}/inquiries", json={"name": "Pat", "message": "Me too"}
    )
    assert signed_in.status_code == 201, signed_in.text
    joined = lead_for(db, listing, email)
    assert joined.id == lead.id
    assert joined.user_id is not None
    assert [(e.kind, e.verified) for e in timeline(db, listing, lead.id)] == [
        ("inquiry", False),
        ("inquiry", True),
    ]


def test_approving_a_hold_moves_the_lead_to_holding(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    created = buyer.post(f"/v1/lots/{listing.available}/hold-requests", json={"name": "Pat"})
    assert created.status_code == 201, created.text
    decided = alpha_owner.post(
        f"/v1/tenants/{listing.tenant.tenant_id}/hold-requests/{created.json()['id']}/decision",
        json={"decision": "approve"},
    )
    assert decided.status_code == 200, decided.text

    lead = lead_for(db, listing, email_of(buyer))
    assert (lead.stage, lead.source) == ("holding", "hold_request")
    events = {e.kind: e for e in timeline(db, listing, lead.id)}
    assert set(events) == {"hold_requested", "hold_approved", "stage_changed"}
    assert events["hold_approved"].actor_user_id == listing.tenant.owner_id
    assert events["stage_changed"].detail == {"from": "new", "to": "holding"}


def test_owners_change_stages_and_add_notes_but_never_rewrite_the_timeline(
    buyer: TestClient, listing: Listing, db: Databases
) -> None:
    sent = buyer.post(
        f"/v1/lots/{listing.available}/inquiries", json={"name": "Pat", "message": "Hello"}
    )
    assert sent.status_code == 201, sent.text
    lead = lead_for(db, listing, email_of(buyer))
    owner = listing.tenant

    with user_session(owner.owner_id, owner.tenant_id, engine=db.api) as session:
        session.execute(text("UPDATE leads SET stage = 'won' WHERE id = :id"), {"id": lead.id})
        session.execute(
            text(
                "INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id, detail)"
                " VALUES (:t, :l, 'note', :o, '{\"text\": \"Called; signing Friday\"}')"
            ),
            {"t": owner.tenant_id, "l": lead.id, "o": owner.owner_id},
        )
    events = timeline(db, listing, lead.id)
    assert [e.kind for e in events][-2:] in (["note", "stage_changed"], ["stage_changed", "note"])
    stage = next(e for e in events if e.kind == "stage_changed")
    assert (stage.actor_user_id, stage.detail) == (owner.owner_id, {"from": "new", "to": "won"})

    forbidden = (
        # Only notes, and only as yourself.
        "INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id)"
        " VALUES (:t, :l, 'inquiry', :o)",
        # Only the stage changes; the buyer's details come from their activity.
        "UPDATE leads SET email = 'other@example.test' WHERE id = :l",
        # The timeline is append-only.
        "UPDATE lead_events SET detail = '{}' WHERE lead_id = :l",
        "DELETE FROM lead_events WHERE lead_id = :l",
    )
    for sql in forbidden:
        with (
            pytest.raises(ProgrammingError, match=r"row-level security|permission denied"),
            user_session(owner.owner_id, owner.tenant_id, engine=db.api) as session,
        ):
            session.execute(text(sql), {"t": owner.tenant_id, "l": lead.id, "o": owner.owner_id})
