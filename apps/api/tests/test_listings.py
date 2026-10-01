"""P1-04: owner portal CRUD for subdivisions, phases and lots, with status and price history."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE
from cornerpin.listings.schemas import RESERVED_SLUGS
from cornerpin.main import create_app

from .conftest import Databases, TenantData

Json = dict[str, Any]


@pytest.fixture
def alpha_owner(db: Databases, tenants: tuple[TenantData, TenantData]) -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        signed_in = service.sign_in_verified_email("owner@alpha.test", None, "/app", "pytest")
        client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        yield client


def base(tenant: TenantData) -> str:
    return f"/v1/tenants/{tenant.tenant_id}"


def new_subdivision(client: TestClient, tenant: TenantData, **overrides: Any) -> Json:
    body = {
        "name": "Sage Hollow",
        "slug": f"sage-{uuid4().hex[:8]}",
        "time_zone": "America/Boise",
        "latitude": 43.6,
        "longitude": -116.2,
    } | overrides
    response = client.post(f"{base(tenant)}/subdivisions", json=body)
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


def new_phase(client: TestClient, tenant: TenantData, subdivision_id: str, name: str) -> Json:
    response = client.post(
        f"{base(tenant)}/subdivisions/{subdivision_id}/phases", json={"name": name}
    )
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


def new_lot(client: TestClient, tenant: TenantData, subdivision_id: str, **fields: Any) -> Json:
    response = client.post(f"{base(tenant)}/subdivisions/{subdivision_id}/lots", json=fields)
    assert response.status_code == 201, response.text
    created: Json = response.json()
    return created


# --- acceptance: create a lot, change status, see the history -------------------------------


def test_create_lot_change_status_and_price_see_history(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, subdivision["id"], "Phase 1")
    lot = new_lot(
        alpha_owner, alpha, subdivision["id"], number="12", phase_id=phase["id"], price=95000
    )
    assert lot["status"] == "available"
    assert len(lot["status_history"]) == 1

    changed = alpha_owner.patch(
        f"{base(alpha)}/lots/{lot['id']}", json={"status": "on_hold", "price": 89000}
    )
    assert changed.status_code == 200, changed.text
    detail = changed.json()

    assert detail["status"] == "on_hold"
    assert detail["price"] == 89000
    latest_status = detail["status_history"][0]
    assert (latest_status["from_status"], latest_status["to_status"]) == ("available", "on_hold")
    assert latest_status["changed_by_email"] == "owner@alpha.test"
    latest_price = detail["price_history"][0]
    assert (latest_price["from_price"], latest_price["to_price"]) == (95000, 89000)
    assert [c["to_status"] for c in detail["status_history"]] == ["on_hold", "available"]


def test_unchanged_status_adds_no_history(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, subdivision["id"], "Phase 1")
    lot = new_lot(alpha_owner, alpha, subdivision["id"], number="1", phase_id=phase["id"])
    detail = alpha_owner.patch(
        f"{base(alpha)}/lots/{lot['id']}", json={"acreage": 1.25, "published": True}
    ).json()
    assert len(detail["status_history"]) == 1
    assert len(detail["price_history"]) == 1
    assert detail["acreage"] == 1.25


def test_subdivision_detail_lists_phases_and_lots_in_number_order(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, subdivision["id"], "Phase 1")
    for number in ("10", "2", "B-1", "1"):
        new_lot(alpha_owner, alpha, subdivision["id"], number=number, phase_id=phase["id"])

    detail = alpha_owner.get(f"{base(alpha)}/subdivisions/{subdivision['id']}").json()
    assert [lot["number"] for lot in detail["lots"]] == ["1", "2", "10", "B-1"]
    assert detail["phases"][0]["lot_count"] == 4
    assert (detail["latitude"], detail["longitude"]) == pytest.approx((43.6, -116.2))

    listed = alpha_owner.get(f"{base(alpha)}/subdivisions").json()
    mine = next(s for s in listed if s["id"] == subdivision["id"])
    assert (mine["lot_count"], mine["available_count"]) == (4, 4)


def test_update_subdivision(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    response = alpha_owner.patch(
        f"{base(alpha)}/subdivisions/{subdivision['id']}",
        json={"name": "Sage Hollow North", "latitude": 47.7, "longitude": -116.8,
              "time_zone": "America/Los_Angeles", "published": True},
    )  # fmt: skip
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["name"] == "Sage Hollow North"
    assert updated["time_zone"] == "America/Los_Angeles"
    assert updated["published"] is True
    assert (updated["latitude"], updated["longitude"]) == pytest.approx((47.7, -116.8))


def test_home_details_only_on_lot_and_home(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, subdivision["id"], "Phase 1")
    refused = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{subdivision['id']}/lots",
        json={"number": "7", "phase_id": phase["id"], "home": {"bedrooms": 3}},
    )
    assert refused.status_code == 422

    lot = new_lot(
        alpha_owner,
        alpha,
        subdivision["id"],
        number="7",
        phase_id=phase["id"],
        listing_type="lot_and_home",
        home={"bedrooms": 4, "bathrooms": 2.5, "square_feet": 2400},
    )
    assert lot["home"]["bathrooms"] == 2.5

    land = alpha_owner.patch(
        f"{base(alpha)}/lots/{lot['id']}", json={"listing_type": "land_only"}
    ).json()
    assert land["home"] is None


# --- validation and conflicts --------------------------------------------------------------


def test_reserved_and_duplicate_slugs(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    reserved = alpha_owner.post(
        f"{base(alpha)}/subdivisions",
        json={"name": "x", "slug": "app", "time_zone": "America/Boise",
              "latitude": 43, "longitude": -116},
    )  # fmt: skip
    assert reserved.status_code == 422

    taken = new_subdivision(alpha_owner, alpha)["slug"]
    duplicate = alpha_owner.post(
        f"{base(alpha)}/subdivisions",
        json={"name": "x", "slug": taken, "time_zone": "America/Boise",
              "latitude": 43, "longitude": -116},
    )  # fmt: skip
    assert duplicate.status_code == 409
    assert "already taken" in duplicate.json()["detail"]


def test_python_reserved_slugs_match_the_database(db: Databases) -> None:
    with db.owner.connect() as conn:
        for slug in sorted(RESERVED_SLUGS):
            savepoint = conn.begin_nested()
            with pytest.raises(IntegrityError, match="subdivisions_slug_check"):
                conn.execute(
                    text(
                        "INSERT INTO subdivisions (tenant_id, name, slug, location, time_zone)"
                        " SELECT id, 'x', :slug, ST_SetSRID(ST_MakePoint(0, 0), 4326), 'UTC'"
                        " FROM tenants LIMIT 1"
                    ),
                    {"slug": slug},
                )
            savepoint.rollback()
        conn.rollback()


def test_unknown_time_zone_is_refused(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    response = alpha_owner.post(
        f"{base(alpha)}/subdivisions",
        json={"name": "x", "slug": f"tz-{uuid4().hex[:6]}", "time_zone": "Mountain",
              "latitude": 43, "longitude": -116},
    )  # fmt: skip
    assert response.status_code == 422


def test_duplicate_lot_number_and_foreign_phase(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    first = new_subdivision(alpha_owner, alpha)
    second = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, first["id"], "Phase 1")
    other_phase = new_phase(alpha_owner, alpha, second["id"], "Phase 1")
    new_lot(alpha_owner, alpha, first["id"], number="3", phase_id=phase["id"])

    duplicate = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{first['id']}/lots",
        json={"number": "3", "phase_id": phase["id"]},
    )
    assert duplicate.status_code == 409

    wrong_phase = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{first['id']}/lots",
        json={"number": "4", "phase_id": other_phase["id"]},
    )
    assert wrong_phase.status_code == 422


# --- deleting ------------------------------------------------------------------------------


def test_delete_refused_while_in_use(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    phase = new_phase(alpha_owner, alpha, subdivision["id"], "Phase 1")
    lot = new_lot(alpha_owner, alpha, subdivision["id"], number="5", phase_id=phase["id"])

    assert alpha_owner.delete(f"{base(alpha)}/subdivisions/{subdivision['id']}").status_code == 409
    assert alpha_owner.delete(f"{base(alpha)}/phases/{phase['id']}").status_code == 409

    assert alpha_owner.delete(f"{base(alpha)}/lots/{lot['id']}").status_code == 204
    assert alpha_owner.delete(f"{base(alpha)}/phases/{phase['id']}").status_code == 204
    assert alpha_owner.delete(f"{base(alpha)}/subdivisions/{subdivision['id']}").status_code == 204
    assert alpha_owner.get(f"{base(alpha)}/subdivisions/{subdivision['id']}").status_code == 404


def test_lot_with_buyer_activity_cannot_be_deleted(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants  # the fixture lot has an inquiry and a hold request
    response = alpha_owner.delete(f"{base(alpha)}/lots/{alpha.lot_id}")
    assert response.status_code == 409
    assert "inquiries or hold requests" in response.json()["detail"]
    assert alpha_owner.get(f"{base(alpha)}/lots/{alpha.lot_id}").status_code == 200


# --- tenant isolation ----------------------------------------------------------------------


def test_owner_cannot_touch_another_tenants_listings(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    # Through the other tenant's path: not a member.
    assert alpha_owner.get(f"{base(bravo)}/subdivisions").status_code == 404
    assert alpha_owner.get(f"{base(bravo)}/lots/{bravo.lot_id}").status_code == 404
    # Through their own path with the other tenant's ids: RLS hides the rows.
    assert alpha_owner.get(f"{base(alpha)}/lots/{bravo.lot_id}").status_code == 404
    patched = alpha_owner.patch(f"{base(alpha)}/lots/{bravo.lot_id}", json={"status": "sold"})
    assert patched.status_code == 404
    deleted = alpha_owner.delete(f"{base(alpha)}/subdivisions/{bravo.subdivision_id}")
    assert deleted.status_code == 404
    created = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{bravo.subdivision_id}/lots",
        json={"number": "99", "phase_id": str(uuid4())},
    )
    assert created.status_code == 404


def test_buyers_and_visitors_have_no_portal(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    with TestClient(create_app()) as client:
        assert client.get(f"{base(alpha)}/subdivisions").status_code == 401
        signed_in = service.sign_in_verified_email("buyer@alpha.test", None, "/", "pytest")
        client.cookies.set(SESSION_COOKIE, signed_in.session_token)
        assert client.get(f"{base(alpha)}/subdivisions").status_code == 404
