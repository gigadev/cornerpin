"""P1-07: what the public pages read. Unpublished lots never appear: not in GraphQL, and not
through a direct link to one of their files."""

import io
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cornerpin.main import create_app

from .conftest import TenantData

Json = dict[str, Any]
LNG, LAT = -116.2, 43.6
PDF = b"%PDF-1.4\n%%EOF\n"

LOT_QUERY = """
query Lot($slug: String!, $number: String!) {
  lot(subdivisionSlug: $slug, number: $number) {
    number status listingType price acreage phaseName location
    home { bedrooms bathrooms squareFeet description }
    photos { url caption width height }
    documents { kind title sizeBytes url }
  }
}
"""


def base(tenant: TenantData) -> str:
    return f"/v1/tenants/{tenant.tenant_id}"


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (30, 20), (90, 120, 60)).save(out, "PNG")
    return out.getvalue()


def graphql(query: str, **variables: Any) -> Json:
    with TestClient(create_app()) as client:
        body: Json = client.post("/graphql", json={"query": query, "variables": variables}).json()
    assert "errors" not in body, body
    data: Json = body["data"]
    return data


def public_get(path: str) -> Any:
    with TestClient(create_app()) as client:
        return client.get(path)


def square(west: float = LNG, south: float = LAT) -> Json:
    ring = [[west, south], [west + 0.0008, south], [west + 0.0008, south + 0.0006],
            [west, south + 0.0006], [west, south]]  # fmt: skip
    return {"type": "Polygon", "coordinates": [ring]}


@pytest.fixture
def listing(alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]) -> Json:
    """A published subdivision with a published lot + home (shape, two photos, a document)
    and an unpublished lot (with a photo)."""
    alpha, _ = tenants
    subdivision = alpha_owner.post(
        f"{base(alpha)}/subdivisions",
        json={"name": "Public", "slug": f"public-{uuid4().hex[:8]}", "time_zone": "America/Boise",
              "latitude": LAT, "longitude": LNG, "published": True},
    ).json()  # fmt: skip
    phase = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{subdivision['id']}/phases", json={"name": "Phase One"}
    ).json()

    def lot(number: str, **fields: Any) -> str:
        created = alpha_owner.post(
            f"{base(alpha)}/subdivisions/{subdivision['id']}/lots",
            json={"number": number, "phase_id": phase["id"], **fields},
        )
        assert created.status_code == 201, created.text
        lot_id: str = created.json()["id"]
        return lot_id

    shown = lot("7", published=True, price=525000, listing_type="lot_and_home",
                home={"bedrooms": 4, "bathrooms": 2.5, "square_feet": 2400})  # fmt: skip
    hidden = lot("8", published=False, price=90000)
    alpha_owner.put(f"{base(alpha)}/lots/{shown}/boundary", json={"boundary": square()})
    for caption in ("Front", "Back"):
        alpha_owner.post(
            f"{base(alpha)}/lots/{shown}/photos",
            files={"file": ("p.png", png(), "image/png")},
            data={"caption": caption},
        )
    document = alpha_owner.post(
        f"{base(alpha)}/lots/{shown}/documents",
        files={"file": ("plat.pdf", PDF, "application/pdf")},
        data={"kind": "plat", "title": "Recorded plat"},
    ).json()
    hidden_photo = alpha_owner.post(
        f"{base(alpha)}/lots/{hidden}/photos", files={"file": ("p.png", png(), "image/png")}
    ).json()
    return {
        "slug": subdivision["slug"],
        "subdivision_id": subdivision["id"],
        "shown": shown,
        "hidden": hidden,
        "document_id": document["id"],
        "hidden_photo_id": hidden_photo["id"],
    }


def test_lot_detail_has_everything_the_page_shows(listing: Json) -> None:
    lot = graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"]
    assert (lot["status"], lot["listingType"], lot["price"]) == (
        "AVAILABLE",
        "LOT_AND_HOME",
        525000,
    )
    assert lot["phaseName"] == "Phase One"
    assert lot["home"] == {"bedrooms": 4, "bathrooms": 2.5, "squareFeet": 2400, "description": None}
    assert [photo["caption"] for photo in lot["photos"]] == ["Front", "Back"]
    assert lot["photos"][0]["url"].startswith("/v1/public/photos/")
    assert lot["documents"] == [
        {"kind": "PLAT", "title": "Recorded plat", "sizeBytes": len(PDF),
         "url": f"/v1/public/documents/{listing['document_id']}/file"},
    ]  # fmt: skip
    # Directions point inside the lot's shape.
    lng, lat = lot["location"]
    assert LNG < lng < LNG + 0.0008 and LAT < lat < LAT + 0.0006


def test_public_files_download(listing: Json) -> None:
    lot = graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"]
    photo = public_get(lot["photos"][0]["url"])
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert photo.headers["cache-control"].startswith("public")
    document = public_get(lot["documents"][0]["url"])
    assert document.content == PDF
    assert 'filename="Recorded plat.pdf"' in document.headers["content-disposition"]


def test_unpublished_lot_never_appears(listing: Json) -> None:
    assert graphql(LOT_QUERY, slug=listing["slug"], number="8")["lot"] is None
    numbers = graphql(
        "query($slug: String!) { subdivision(slug: $slug) { lots { number } } }",
        slug=listing["slug"],
    )["subdivision"]["lots"]
    assert [lot["number"] for lot in numbers] == ["7"]
    # Not even through a direct link to its photo.
    assert public_get(f"/v1/public/photos/{listing['hidden_photo_id']}/file").status_code == 404


def test_unpublishing_the_subdivision_hides_everything(
    listing: Json, alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    lot = graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"]
    alpha_owner.patch(
        f"{base(alpha)}/subdivisions/{listing['subdivision_id']}", json={"published": False}
    )
    assert graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"] is None
    assert public_get(lot["photos"][0]["url"]).status_code == 404
    assert public_get(lot["documents"][0]["url"]).status_code == 404


def test_lot_without_a_shape_points_at_the_subdivision(
    listing: Json, alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    alpha_owner.delete(f"{base(alpha)}/lots/{listing['shown']}/boundary")
    lot = graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"]
    assert lot["location"] == pytest.approx([LNG, LAT])


def test_land_only_lots_have_no_home(listing: Json, alpha_owner: TestClient,
                                     tenants: tuple[TenantData, TenantData]) -> None:  # fmt: skip
    alpha, _ = tenants
    alpha_owner.patch(f"{base(alpha)}/lots/{listing['shown']}", json={"listing_type": "land_only"})
    assert graphql(LOT_QUERY, slug=listing["slug"], number="7")["lot"]["home"] is None


def test_unknown_lots_and_subdivisions_are_null(listing: Json) -> None:
    assert graphql(LOT_QUERY, slug=listing["slug"], number="99")["lot"] is None
    assert graphql(LOT_QUERY, slug="no-such-place", number="7")["lot"] is None
    assert public_get(f"/v1/public/photos/{uuid4()}/file").status_code == 404
