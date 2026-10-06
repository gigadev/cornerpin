"""P1-05: upload, reorder and caption photos; upload and download documents."""

import io
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from cornerpin.core.db import user_session
from cornerpin.core.outbox import drain
from cornerpin.core.storage import get_storage
from cornerpin.listings import media_routes

from .conftest import Databases, TenantData

Json = dict[str, Any]
ORIENTATION = 0x0112
MAKE = 0x010F
GPS_IFD = 0x8825
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def jpeg(width: int, height: int, *, orientation: int | None = None) -> bytes:
    """A JPEG with camera metadata: maker, GPS position and optionally a rotation flag."""
    exif = Image.Exif()
    exif[MAKE] = "TestCam"
    exif[GPS_IFD] = {1: "N", 2: (43.0, 36.0, 0.0), 3: "W", 4: (116.0, 12.0, 0.0)}
    if orientation:
        exif[ORIENTATION] = orientation
    out = io.BytesIO()
    Image.new("RGB", (width, height), (120, 140, 90)).save(out, "JPEG", exif=exif)
    return out.getvalue()


def png(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 180, 150)).save(out, "PNG")
    return out.getvalue()


def base(tenant: TenantData) -> str:
    return f"/v1/tenants/{tenant.tenant_id}"


@pytest.fixture
def lot(alpha_owner: TestClient, tenants: tuple[TenantData, TenantData]) -> str:
    """A fresh lot in the alpha tenant, with no photos or documents."""
    alpha, _ = tenants
    subdivision = alpha_owner.post(
        f"{base(alpha)}/subdivisions",
        json={"name": "Media", "slug": f"media-{uuid4().hex[:8]}", "time_zone": "America/Boise",
              "latitude": 43.6, "longitude": -116.2},
    ).json()  # fmt: skip
    phase = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{subdivision['id']}/phases", json={"name": "Phase 1"}
    ).json()
    created = alpha_owner.post(
        f"{base(alpha)}/subdivisions/{subdivision['id']}/lots",
        json={"number": "1", "phase_id": phase["id"]},
    ).json()
    lot_id: str = created["id"]
    return lot_id


def upload_photo(
    client: TestClient, tenant: TenantData, lot_id: str, data: bytes, caption: str = ""
) -> Json:
    response = client.post(
        f"{base(tenant)}/lots/{lot_id}/photos",
        files={"file": ("photo.jpg", data, "image/jpeg")},
        data={"caption": caption},
    )
    assert response.status_code == 201, response.text
    photo: Json = response.json()
    return photo


def stored_image(client: TestClient, photo: Json) -> Image.Image:
    response = client.get(photo["url"])
    assert response.status_code == 200
    return Image.open(io.BytesIO(response.content))


# --- photos --------------------------------------------------------------------------------


def test_photo_is_turned_upright_and_stripped_of_metadata(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    # Orientation 6: the camera was turned; the pixels are 300x200 but upright is 200x300.
    photo = upload_photo(alpha_owner, alpha, lot, jpeg(300, 200, orientation=6))

    assert (photo["width"], photo["height"]) == (200, 300)
    image = stored_image(alpha_owner, photo)
    assert image.size == (200, 300)
    exif = image.getexif()
    assert MAKE not in exif
    assert ORIENTATION not in exif
    assert not exif.get_ifd(GPS_IFD)


def test_large_photo_is_scaled_down(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    photo = upload_photo(alpha_owner, alpha, lot, png(4000, 1000))
    assert (photo["width"], photo["height"]) == (2560, 640)
    assert photo["content_type"] == "image/png"


def test_photo_file_is_private_and_cacheable(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    photo = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    response = alpha_owner.get(photo["url"])
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"].startswith("private")


@pytest.mark.parametrize(
    ("name", "data"),
    [("notes.txt", b"just some text"), ("animation.gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;")],
)
def test_only_jpeg_png_and_webp_photos(
    alpha_owner: TestClient,
    tenants: tuple[TenantData, TenantData],
    lot: str,
    name: str,
    data: bytes,
) -> None:
    alpha, _ = tenants
    response = alpha_owner.post(
        f"{base(alpha)}/lots/{lot}/photos", files={"file": (name, data, "image/jpeg")}
    )
    assert response.status_code == 422


def test_oversized_upload_is_refused(
    alpha_owner: TestClient,
    tenants: tuple[TenantData, TenantData],
    lot: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alpha, _ = tenants
    monkeypatch.setattr(media_routes, "MAX_PHOTO_BYTES", 1024)
    response = alpha_owner.post(
        f"{base(alpha)}/lots/{lot}/photos",
        files={"file": ("big.png", png(400, 400) + b"\0" * 2048, "image/png")},
    )
    assert response.status_code == 413


def test_caption_and_reorder(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    first = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30), caption="Front")
    second = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30), caption="Back")
    third = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    assert [p["sort_order"] for p in (first, second, third)] == [0, 1, 2]

    captioned = alpha_owner.patch(
        f"{base(alpha)}/photos/{third['id']}", json={"caption": "  View east  "}
    )
    assert captioned.json()["caption"] == "View east"

    order = [third["id"], first["id"], second["id"]]
    reordered = alpha_owner.put(f"{base(alpha)}/lots/{lot}/photos/order", json={"photo_ids": order})
    assert reordered.status_code == 200
    assert [p["id"] for p in reordered.json()] == order

    listed = alpha_owner.get(f"{base(alpha)}/lots/{lot}/photos").json()
    assert [p["caption"] for p in listed] == ["View east", "Front", "Back"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "foreign"])
def test_reorder_must_name_each_photo_once(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str, change: str
) -> None:
    alpha, _ = tenants
    first = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    second = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    ids = {
        "missing": [first["id"]],
        "duplicate": [first["id"], first["id"], second["id"]],
        "foreign": [first["id"], second["id"], str(uuid4())],
    }[change]
    response = alpha_owner.put(f"{base(alpha)}/lots/{lot}/photos/order", json={"photo_ids": ids})
    assert response.status_code == 422


def test_deleted_photo_file_is_removed_by_the_outbox(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str, db: Databases
) -> None:
    alpha, _ = tenants
    photo = upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    with db.owner.connect() as conn:
        key = conn.execute(
            text("SELECT storage_key FROM lot_media WHERE id = :id"), {"id": photo["id"]}
        ).scalar_one()

    assert alpha_owner.delete(f"{base(alpha)}/photos/{photo['id']}").status_code == 204
    assert alpha_owner.get(photo["url"]).status_code == 404
    assert get_storage().get(key)  # still there until the outbox runs

    drain()  # everything due, whatever earlier tests queued
    with pytest.raises(FileNotFoundError):
        get_storage().get(key)


# --- documents -----------------------------------------------------------------------------


def test_document_uploads_and_downloads_under_its_title(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    uploaded = alpha_owner.post(
        f"{base(alpha)}/lots/{lot}/documents",
        files={"file": ("scan0042.pdf", PDF, "application/pdf")},
        data={"kind": "plat", "title": "Recorded plat"},
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert (document["kind"], document["size_bytes"]) == ("plat", len(PDF))

    download = alpha_owner.get(document["url"])
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"
    assert 'filename="Recorded plat.pdf"' in download.headers["content-disposition"]

    listed = alpha_owner.get(f"{base(alpha)}/lots/{lot}/documents").json()
    assert [d["title"] for d in listed] == ["Recorded plat"]


def test_document_type_is_checked_from_its_contents(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str
) -> None:
    alpha, _ = tenants
    response = alpha_owner.post(
        f"{base(alpha)}/lots/{lot}/documents",
        files={"file": ("plat.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")},
        data={"kind": "plat", "title": "Plat"},
    )
    assert response.status_code == 422


def test_deleting_a_lot_removes_its_files(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], lot: str, db: Databases
) -> None:
    alpha, _ = tenants
    upload_photo(alpha_owner, alpha, lot, jpeg(40, 30))
    alpha_owner.post(
        f"{base(alpha)}/lots/{lot}/documents",
        files={"file": ("p.pdf", PDF, "application/pdf")},
        data={"kind": "survey", "title": "Survey"},
    )
    with db.owner.connect() as conn:
        keys = (
            conn.execute(
                text(
                    "SELECT storage_key FROM lot_media WHERE lot_id = :l"
                    " UNION ALL SELECT storage_key FROM lot_documents WHERE lot_id = :l"
                ),
                {"l": lot},
            )
            .scalars()
            .all()
        )
    assert len(keys) == 2

    assert alpha_owner.delete(f"{base(alpha)}/lots/{lot}").status_code == 204
    drain()  # everything due, whatever earlier tests queued
    for key in keys:
        with pytest.raises(FileNotFoundError):
            get_storage().get(key)


# --- isolation -----------------------------------------------------------------------------


def test_another_tenants_media_is_out_of_reach(
    alpha_owner: TestClient, tenants: tuple[TenantData, TenantData], db: Databases
) -> None:
    alpha, bravo = tenants
    with db.owner.connect() as conn:
        bravo_photo = conn.execute(
            text("SELECT id FROM lot_media WHERE tenant_id = :t LIMIT 1"), {"t": bravo.tenant_id}
        ).scalar_one()
        bravo_document = conn.execute(
            text("SELECT id FROM lot_documents WHERE tenant_id = :t LIMIT 1"),
            {"t": bravo.tenant_id},
        ).scalar_one()

    assert alpha_owner.get(f"{base(alpha)}/photos/{bravo_photo}/file").status_code == 404
    assert alpha_owner.get(f"{base(alpha)}/documents/{bravo_document}/file").status_code == 404
    assert alpha_owner.get(f"{base(bravo)}/photos/{bravo_photo}/file").status_code == 404
    assert alpha_owner.delete(f"{base(alpha)}/photos/{bravo_photo}").status_code == 404
    upload = alpha_owner.post(
        f"{base(alpha)}/lots/{bravo.lot_id}/photos",
        files={"file": ("x.jpg", jpeg(10, 10), "image/jpeg")},
    )
    assert upload.status_code == 404


def test_signed_in_users_cannot_queue_sign_in_emails(
    db: Databases, tenants: tuple[TenantData, TenantData]
) -> None:
    alpha, _ = tenants
    with (
        pytest.raises(ProgrammingError, match="row-level security"),
        user_session(alpha.owner_id, alpha.tenant_id, engine=db.api) as session,
    ):
        session.execute(
            text(
                "INSERT INTO outbox (event_type, payload) VALUES"
                " ('auth.magic_link_requested', '{}'::jsonb)"
            )
        )
