"""P1-06: lot boundaries round-trip through PostGIS, GeoJSON import, the plat overlay, and the
public GraphQL map. The fixture subdivisions sit at longitude -116.2, latitude 43.6."""

import io
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from cornerpin.main import create_app

from .conftest import Databases, TenantData

Json = dict[str, Any]
LNG, LAT = -116.2, 43.6
# About 63 m x 70 m: roughly an acre at this latitude.
D_LNG, D_LAT = 0.00079, 0.00063


def square(west: float = LNG, south: float = LAT, size: float = 1.0) -> Json:
    # Rounded like PostGIS output (7 decimals, about 1 cm), so round trips compare exactly.
    west, south = round(west, 7), round(south, 7)
    east, north = round(west + D_LNG * size, 7), round(south + D_LAT * size, 7)
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def base(tenant: TenantData) -> str:
    return f"/v1/tenants/{tenant.tenant_id}"


def new_subdivision(client: TestClient, tenant: TenantData, *, published: bool = False) -> Json:
    subdivision: Json = client.post(
        f"{base(tenant)}/subdivisions",
        json={"name": "Geo", "slug": f"geo-{uuid4().hex[:8]}", "time_zone": "America/Boise",
              "latitude": LAT, "longitude": LNG, "published": published},
    ).json()  # fmt: skip
    phase = client.post(
        f"{base(tenant)}/subdivisions/{subdivision['id']}/phases", json={"name": "Phase 1"}
    ).json()
    subdivision["phase_id"] = phase["id"]
    return subdivision


def new_lot(
    client: TestClient, tenant: TenantData, subdivision: Json, number: str, **extra: Any
) -> str:
    response = client.post(
        f"{base(tenant)}/subdivisions/{subdivision['id']}/lots",
        json={"number": number, "phase_id": subdivision["phase_id"], **extra},
    )
    assert response.status_code == 201, response.text
    lot_id: str = response.json()["id"]
    return lot_id


# --- boundaries ----------------------------------------------------------------------------


def test_drawn_boundary_round_trips_through_postgis(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], db: Databases
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    lot_id = new_lot(alpha_owner, alpha, subdivision, "1", acreage=9.9)

    saved = alpha_owner.put(f"{base(alpha)}/lots/{lot_id}/boundary", json={"boundary": square()})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["boundary"]["type"] == "MultiPolygon"
    assert body["boundary"]["coordinates"][0] == square()["coordinates"]
    assert body["acreage"] == pytest.approx(1.1, abs=0.1)  # from the shape, not the 9.9 typed in
    assert body["overlaps"] == []

    with db.owner.connect() as conn:
        row = conn.execute(
            text(
                "SELECT GeometryType(boundary), ST_SRID(boundary), ST_IsValid(boundary)"
                " FROM lots WHERE id = :id"
            ),
            {"id": lot_id},
        ).one()
    assert tuple(row) == ("MULTIPOLYGON", 4326, True)

    lot = alpha_owner.get(f"{base(alpha)}/lots/{lot_id}").json()
    assert lot["acreage"] == body["acreage"]


def test_clearing_a_boundary_keeps_the_last_acreage(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    lot_id = new_lot(alpha_owner, alpha, subdivision, "1")
    acreage = alpha_owner.put(
        f"{base(alpha)}/lots/{lot_id}/boundary", json={"boundary": square()}
    ).json()["acreage"]

    cleared = alpha_owner.delete(f"{base(alpha)}/lots/{lot_id}/boundary").json()
    assert cleared["boundary"] is None
    assert cleared["acreage"] == acreage


def test_overlapping_lots_are_reported_not_refused(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    first = new_lot(alpha_owner, alpha, subdivision, "1")
    second = new_lot(alpha_owner, alpha, subdivision, "2")
    neighbour = new_lot(alpha_owner, alpha, subdivision, "3")
    alpha_owner.put(f"{base(alpha)}/lots/{first}/boundary", json={"boundary": square()})

    # Sharing an edge is normal and not an overlap.
    beside = alpha_owner.put(
        f"{base(alpha)}/lots/{neighbour}/boundary",
        json={"boundary": square(west=LNG + D_LNG)},
    ).json()
    assert beside["overlaps"] == []

    overlapping = alpha_owner.put(
        f"{base(alpha)}/lots/{second}/boundary",
        json={"boundary": square(west=LNG + D_LNG / 2)},
    )
    assert overlapping.status_code == 200
    assert overlapping.json()["overlaps"] == ["1", "3"]


@pytest.mark.parametrize(
    ("shape", "message"),
    [
        (  # a bow tie: the edges cross
            {"type": "Polygon", "coordinates": [[[LNG, LAT], [LNG + 0.001, LAT + 0.001],
             [LNG + 0.001, LAT], [LNG, LAT + 0.001], [LNG, LAT]]]},
            "isn't valid",
        ),
        (square(west=LAT, south=LNG), "Coordinates must be longitude/latitude"),  # swapped
        (square(west=-117.2), "km from the subdivision"),
        (  # Idaho state plane feet, not longitude/latitude
            {"type": "Polygon", "coordinates": [[[2300000, 1400000], [2300200, 1400000],
             [2300200, 1400200], [2300000, 1400000]]]},
            "Coordinates must be longitude/latitude",
        ),
        ({"type": "Point", "coordinates": [LNG, LAT]}, ""),
    ],
)  # fmt: skip
def test_bad_shapes_are_refused(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], shape: Json, message: str
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    lot_id = new_lot(alpha_owner, alpha, subdivision, "1")
    response = alpha_owner.put(f"{base(alpha)}/lots/{lot_id}/boundary", json={"boundary": shape})
    assert response.status_code == 422
    assert message in response.text


def test_map_lists_every_lot_with_its_shape(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    drawn = new_lot(alpha_owner, alpha, subdivision, "1")
    new_lot(alpha_owner, alpha, subdivision, "2")
    alpha_owner.put(f"{base(alpha)}/lots/{drawn}/boundary", json={"boundary": square()})

    the_map = alpha_owner.get(f"{base(alpha)}/subdivisions/{subdivision['id']}/map").json()
    assert the_map["center"] == pytest.approx([LNG, LAT])
    by_number = {lot["number"]: lot for lot in the_map["lots"]}
    assert by_number["1"]["boundary"]["type"] == "MultiPolygon"
    assert by_number["2"]["boundary"] is None
    assert the_map["overlay"] is None


def test_another_tenants_lot_cannot_be_drawn(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, bravo = tenants
    response = alpha_owner.put(
        f"{base(alpha)}/lots/{bravo.lot_id}/boundary", json={"boundary": square()}
    )
    assert response.status_code == 404
    assert (
        alpha_owner.get(f"{base(bravo)}/subdivisions/{bravo.subdivision_id}/map").status_code == 404
    )


# --- GeoJSON import ------------------------------------------------------------------------


def feature(properties: Json | None, geometry: Json | None) -> Json:
    return {"type": "Feature", "properties": properties, "geometry": geometry}


def test_import_previews_then_applies(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    existing = new_lot(alpha_owner, alpha, subdivision, "7")
    new_lot(alpha_owner, alpha, subdivision, "9")  # not in the file
    collection = {
        "type": "FeatureCollection",
        "features": [
            feature({"LOT": "Lot 7"}, square()),
            feature({"name": 8}, square(west=LNG + D_LNG)),
            feature({"name": "8"}, square(west=LNG + 2 * D_LNG)),
            feature({"owner": "nobody"}, square(west=LNG + 3 * D_LNG)),
            feature({"number": "10"}, {"type": "LineString",
                                       "coordinates": [[LNG, LAT], [LNG, LAT + 0.001]]}),
            feature({"number": "11"}, square(west=-110.0)),
        ],
    }  # fmt: skip
    url = f"{base(alpha)}/subdivisions/{subdivision['id']}/import"

    preview = alpha_owner.post(url, json={"collection": collection})
    assert preview.status_code == 200, preview.text
    report = preview.json()
    assert report["applied"] is False
    actions = [(row["number"], row["action"]) for row in report["rows"]]
    assert actions == [
        ("7", "update"),
        ("8", "skip"),  # no lot 8 and no phase to create it in
        ("8", "skip"),  # duplicate in the file
        (None, "skip"),
        ("10", "skip"),
        ("11", "skip"),
    ]
    assert report["rows"][0]["acreage"] == pytest.approx(1.1, abs=0.1)
    assert "km from the subdivision" in report["rows"][5]["reason"]
    assert report["lots_without_shape"] == ["9"]
    # Nothing saved by a preview.
    assert alpha_owner.get(f"{base(alpha)}/lots/{existing}").json()["acreage"] is None

    applied = alpha_owner.post(
        url,
        json={"collection": collection, "apply": True, "phase_id": subdivision["phase_id"]},
    ).json()
    assert [(row["number"], row["action"]) for row in applied["rows"][:2]] == [
        ("7", "update"),
        ("8", "create"),
    ]
    the_map = alpha_owner.get(f"{base(alpha)}/subdivisions/{subdivision['id']}/map").json()
    drawn = sorted(lot["number"] for lot in the_map["lots"] if lot["boundary"])
    assert drawn == ["7", "8"]


def test_import_refuses_projected_geojson(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    response = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{subdivision['id']}/import",
        json={"collection": {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2241"}},
            "features": [],
        }},
    )  # fmt: skip
    assert response.status_code == 422
    assert "WGS 84" in response.text


# --- plat overlay --------------------------------------------------------------------------


def plat_png(width: int = 300, height: int = 200) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (240, 240, 230)).save(out, "PNG")
    return out.getvalue()


def test_overlay_upload_align_and_remove(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    url = f"{base(alpha)}/subdivisions/{subdivision['id']}/overlay"

    uploaded = alpha_owner.post(url, files={"file": ("plat.png", plat_png(), "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    overlay = uploaded.json()
    corners = overlay["corners"]
    assert len(corners) == 4
    # Placed over the subdivision, wider than tall like the image (300 x 200).
    (west, north), (east, _), (_, south), _ = corners
    assert west < LNG < east and south < LAT < north
    assert alpha_owner.get(overlay["url"]).headers["content-type"] == "image/png"

    moved = [[lng + 0.001, lat] for lng, lat in corners]
    aligned = alpha_owner.patch(url, json={"corners": moved, "opacity": 0.4}).json()
    flat = [value for corner in aligned["corners"] for value in corner]
    assert flat == pytest.approx([value for corner in moved for value in corner])
    assert aligned["opacity"] == pytest.approx(0.4)
    assert alpha_owner.get(f"{url.removesuffix('/overlay')}/map").json()["overlay"][
        "opacity"
    ] == pytest.approx(0.4)

    assert alpha_owner.delete(url).status_code == 204
    assert alpha_owner.get(f"{url}/file").status_code == 404


def test_overlay_corners_must_be_four_lng_lat_pairs(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha)
    url = f"{base(alpha)}/subdivisions/{subdivision['id']}/overlay"
    alpha_owner.post(url, files={"file": ("plat.png", plat_png(), "image/png")})
    assert alpha_owner.patch(url, json={"corners": [[0, 0], [1, 1], [2, 2]]}).status_code == 422
    assert (
        alpha_owner.patch(url, json={"corners": [[0, 0], [1, 1], [2, 2], [500, 0]]}).status_code
        == 422
    )


# --- public GraphQL map --------------------------------------------------------------------

QUERY = """
query Map($slug: String!) {
  subdivision(slug: $slug) {
    name
    center
    lots { number status listingType price acreage boundary }
  }
}
"""


def graphql(slug: str) -> Json:
    with TestClient(create_app()) as client:
        response = client.post("/graphql", json={"query": QUERY, "variables": {"slug": slug}})
    assert response.status_code == 200, response.text
    body: Json = response.json()
    assert "errors" not in body, body
    return body["data"]


def test_drawn_lot_appears_on_the_public_map(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha, published=True)
    shown = new_lot(alpha_owner, alpha, subdivision, "1", published=True, price=90000)
    hidden = new_lot(alpha_owner, alpha, subdivision, "2", published=False)
    for lot_id in (shown, hidden):
        alpha_owner.put(f"{base(alpha)}/lots/{lot_id}/boundary", json={"boundary": square()})

    data = graphql(subdivision["slug"])["subdivision"]
    assert data["center"] == pytest.approx([LNG, LAT])
    assert [lot["number"] for lot in data["lots"]] == ["1"]  # unpublished lot stays hidden
    lot = data["lots"][0]
    assert (lot["status"], lot["listingType"], lot["price"]) == ("AVAILABLE", "LAND_ONLY", 90000)
    assert lot["boundary"]["type"] == "MultiPolygon"
    assert lot["boundary"]["coordinates"][0] == square()["coordinates"]


def test_unpublished_subdivision_is_not_on_the_public_map(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha, published=False)
    assert graphql(subdivision["slug"])["subdivision"] is None
    assert graphql("no-such-place")["subdivision"] is None


def test_public_graphql_is_read_only_and_bounded(db: Databases) -> None:
    with TestClient(create_app()) as client:
        mutation = client.post("/graphql", json={"query": "mutation { x }"})
        assert "errors" in mutation.json()
        normal = 'query { subdivision(slug: "a") { lots { number } } }'
        assert "errors" not in client.post("/graphql", json={"query": normal}).json()
        too_many = "query {" + " ".join(f"a{i}: __typename" for i in range(1500)) + "}"
        assert "errors" in client.post("/graphql", json={"query": too_many}).json()


def test_public_lots_sort_by_number_not_text(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    subdivision = new_subdivision(alpha_owner, alpha, published=True)
    for number in ("10", "B-1", "2"):
        new_lot(alpha_owner, alpha, subdivision, number, published=True)
    lots = graphql(subdivision["slug"])["subdivision"]["lots"]
    assert [lot["number"] for lot in lots] == ["2", "10", "B-1"]
