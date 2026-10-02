"""P1-11: QR codes. A lot's code is stable, and the public lookup follows the lot through a slug
rename; unpublished lots and unknown codes resolve to nothing."""

import re
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cornerpin.listings.qr import ALPHABET, CODE_LENGTH

from .conftest import Databases, Listing

QR_QUERY = "query Qr($code: String!) { qrTarget(code: $code) { subdivisionSlug lotNumber } }"


def code_for(owner: TestClient, listing: Listing, lot_id: str) -> str:
    response = owner.post(f"/v1/tenants/{listing.tenant.tenant_id}/lots/{lot_id}/qr-code")
    assert response.status_code == 200, response.text
    code: str = response.json()["code"]
    return code


def target(client: TestClient, code: str) -> Any:
    body = client.post("/graphql", json={"query": QR_QUERY, "variables": {"code": code}}).json()
    assert "errors" not in body, body
    return body["data"]["qrTarget"]


def subdivision_path(listing: Listing) -> str:
    return f"/v1/tenants/{listing.tenant.tenant_id}/subdivisions/{listing.subdivision_id}"


def test_a_lot_has_one_stable_code(alpha_owner: TestClient, listing: Listing) -> None:
    code = code_for(alpha_owner, listing, listing.available)
    assert re.fullmatch(f"[{ALPHABET}]{{{CODE_LENGTH}}}", code)
    assert code_for(alpha_owner, listing, listing.available) == code
    assert code_for(alpha_owner, listing, listing.sold) != code


def test_the_code_follows_the_lot_through_a_slug_rename(
    alpha_owner: TestClient, anonymous: TestClient, listing: Listing
) -> None:
    code = code_for(alpha_owner, listing, listing.available)
    slug = alpha_owner.get(subdivision_path(listing)).json()["slug"]
    assert target(anonymous, code) == {"subdivisionSlug": slug, "lotNumber": "1"}

    renamed = f"renamed-{uuid4().hex[:8]}"
    response = alpha_owner.patch(subdivision_path(listing), json={"slug": renamed})
    assert response.status_code == 200, response.text
    assert target(anonymous, code) == {"subdivisionSlug": renamed, "lotNumber": "1"}


def test_codes_for_hidden_lots_resolve_to_nothing(
    alpha_owner: TestClient, anonymous: TestClient, listing: Listing
) -> None:
    hidden = code_for(alpha_owner, listing, listing.unpublished)
    assert target(anonymous, hidden) is None

    shown = code_for(alpha_owner, listing, listing.available)
    alpha_owner.patch(subdivision_path(listing), json={"published": False})
    assert target(anonymous, shown) is None


@pytest.mark.parametrize("code", ["zzzzzzzz", "NOT-A-CODE", "a", "x" * 40, "' OR 1=1 --"])
def test_unknown_and_malformed_codes_resolve_to_nothing(anonymous: TestClient, code: str) -> None:
    assert target(anonymous, code) is None


def test_a_deleted_lot_takes_its_code_with_it(
    alpha_owner: TestClient, anonymous: TestClient, listing: Listing
) -> None:
    code = code_for(alpha_owner, listing, listing.available)
    deleted = alpha_owner.delete(f"/v1/tenants/{listing.tenant.tenant_id}/lots/{listing.available}")
    assert deleted.status_code == 204, deleted.text
    assert target(anonymous, code) is None


def test_only_the_owner_can_make_a_code(
    buyer: TestClient,
    client_for: Callable[[str | None], TestClient],
    listing: Listing,
) -> None:
    path = f"/v1/tenants/{listing.tenant.tenant_id}/lots/{listing.available}/qr-code"
    assert buyer.post(path).status_code == 404
    assert client_for("owner@bravo.test").post(path).status_code == 404
    assert client_for(None).post(path).status_code == 401


def test_missing_lot_is_not_found(alpha_owner: TestClient, listing: Listing) -> None:
    response = alpha_owner.post(f"/v1/tenants/{listing.tenant.tenant_id}/lots/{uuid4()}/qr-code")
    assert response.status_code == 404


def test_the_database_allows_one_code_per_lot(db: Databases, listing: Listing) -> None:
    with pytest.raises(IntegrityError), db.owner.begin() as conn:
        for code in ("aaaaaaaa", "bbbbbbbb"):
            conn.execute(
                text("INSERT INTO qr_codes (code, tenant_id, lot_id) VALUES (:c, :t, :l)"),
                {"c": code, "t": listing.tenant.tenant_id, "l": listing.sold},
            )
