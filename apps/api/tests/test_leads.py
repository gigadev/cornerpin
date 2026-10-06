"""P2-01: leads (ADR-035). A buyer's inquiries, holds and consent changes become one lead per
owner, with a timeline, written in the same transaction. Owners read them and add notes and
stage changes; buyers and other tenants see nothing."""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from cornerpin.core.db import user_session

from .conftest import Databases, Listing, TenantData

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


# --- the portal API (P2-02) ----------------------------------------------------------------


def leads_url(lot: Listing, suffix: str = "") -> str:
    return f"/v1/tenants/{lot.tenant.tenant_id}/leads{suffix}"


def asked(buyer: TestClient, lot: Listing, message: str = "Hello") -> str:
    sent = buyer.post(
        f"/v1/lots/{lot.available}/inquiries",
        json={"name": "Pat Buyer", "message": message, "contact": {"email": True}},
    )
    assert sent.status_code == 201, sent.text
    return email_of(buyer)


def test_owners_list_leads_by_stage(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing
) -> None:
    email = asked(buyer, listing)
    listed = alpha_owner.get(leads_url(listing))
    assert listed.status_code == 200, listed.text
    body = listed.json()
    lead = next(lead for lead in body["leads"] if lead["email"] == email)
    assert (lead["stage"], lead["signed_in"], lead["contact"]) == ("new", True, ["email"])
    assert [(lot["number"], lot["subdivision_name"]) for lot in lead["lots"]] == [("1", "Buyers")]
    assert [s["stage"] for s in body["stages"]] == [
        "new", "contacted", "engaged", "holding", "won", "lost",
    ]  # fmt: skip
    assert next(s for s in body["stages"] if s["stage"] == "new")["count"] >= 1

    def emails(**params: Any) -> list[str]:
        found = alpha_owner.get(leads_url(listing), params=params).json()["leads"]
        return [lead["email"] for lead in found]

    assert email in emails(stage="new")
    assert email not in emails(stage="won")
    assert email not in emails(needs_human="true")
    assert alpha_owner.get(leads_url(listing), params={"stage": "maybe"}).status_code == 422


def test_owners_change_a_stage_and_add_notes_through_the_api(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing
) -> None:
    email = asked(buyer, listing)
    lead_id = next(
        lead["id"] for lead in alpha_owner.get(leads_url(listing)).json()["leads"]
        if lead["email"] == email
    )  # fmt: skip

    changed = alpha_owner.patch(leads_url(listing, f"/{lead_id}"), json={"stage": "contacted"})
    assert changed.status_code == 200, changed.text
    latest = changed.json()["events"][0]
    assert (latest["kind"], latest["from_stage"], latest["to_stage"], latest["actor_email"]) == (
        "stage_changed", "new", "contacted", "owner@alpha.test",
    )  # fmt: skip

    noted = alpha_owner.post(
        leads_url(listing, f"/{lead_id}/notes"), json={"text": "  Called; wants Friday  "}
    )
    assert noted.status_code == 201, noted.text
    note = noted.json()["events"][0]
    assert (note["kind"], note["note"], note["by_buyer"]) == ("note", "Called; wants Friday", False)
    inquiry = next(e for e in noted.json()["events"] if e["kind"] == "inquiry")
    assert (inquiry["by_buyer"], inquiry["message"], inquiry["lot"]["number"]) == (
        True, "Hello", "1",
    )  # fmt: skip

    blank = alpha_owner.post(leads_url(listing, f"/{lead_id}/notes"), json={"text": "  "})
    assert blank.status_code == 422


def test_other_tenants_get_not_found(
    buyer: TestClient,
    alpha_owner: TestClient,
    client_for: Callable[[str | None], TestClient],
    listing: Listing,
    tenants: tuple[TenantData, TenantData],
) -> None:
    email = asked(buyer, listing)
    lead_id = next(
        lead["id"] for lead in alpha_owner.get(leads_url(listing)).json()["leads"]
        if lead["email"] == email
    )  # fmt: skip
    _, bravo = tenants
    other = client_for("owner@bravo.test")
    # Their own tenant's URL with alpha's lead, and alpha's URL.
    assert other.get(f"/v1/tenants/{bravo.tenant_id}/leads/{lead_id}").status_code == 404
    assert other.get(leads_url(listing, f"/{lead_id}")).status_code == 404
    patched = other.patch(f"/v1/tenants/{bravo.tenant_id}/leads/{lead_id}", json={"stage": "lost"})
    assert patched.status_code == 404
    assert alpha_owner.get(leads_url(listing, f"/{lead_id}")).json()["stage"] == "new"
    assert buyer.get(leads_url(listing)).status_code == 404  # buyers aren't members


def test_the_needs_a_human_inbox(
    buyer: TestClient, alpha_owner: TestClient, listing: Listing, db: Databases
) -> None:
    email = asked(buyer, listing)
    # The outreach agent hands off in P2-05; until then, set it as it will.
    with db.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE leads SET handoff_at = now(), handoff_reason = 'Asked about financing'"
                " WHERE email = :email AND tenant_id = :t"
            ),
            {"email": email, "t": listing.tenant.tenant_id},
        )

    waiting = alpha_owner.get(leads_url(listing), params={"needs_human": "true"}).json()
    lead = next(lead for lead in waiting["leads"] if lead["email"] == email)
    assert lead["handoff_reason"] == "Asked about financing"
    assert waiting["needs_human"] >= 1
    detail = alpha_owner.get(leads_url(listing, f"/{lead['id']}")).json()
    assert (detail["events"][0]["kind"], detail["events"][0]["reason"]) == (
        "handoff", "Asked about financing",
    )  # fmt: skip

    resolved = alpha_owner.post(leads_url(listing, f"/{lead['id']}/handoff/resolve"))
    assert resolved.status_code == 200, resolved.text
    assert (resolved.json()["handoff_at"], resolved.json()["handoff_reason"]) == (None, None)
    latest = resolved.json()["events"][0]
    assert (latest["kind"], latest["actor_email"]) == ("handoff_resolved", "owner@alpha.test")
    again = alpha_owner.post(leads_url(listing, f"/{lead['id']}/handoff/resolve"))
    assert again.status_code == 409
    still = alpha_owner.get(leads_url(listing), params={"needs_human": "true"}).json()
    assert email not in [lead["email"] for lead in still["leads"]]
