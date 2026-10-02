"""Public photo and document files (ADR-027). Binary files don't fit GraphQL, so these two REST
routes serve them, as cornerpin_public: row-level security makes a file reachable only while its
lot and subdivision are published."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from cornerpin.core.db import public_session
from cornerpin.core.storage import get_storage
from cornerpin.listings.media_routes import attachment
from cornerpin.listings.models import LotDocument, LotPhoto

router = APIRouter(prefix="/public", tags=["public"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Not found, or not published"},
}
# A photo's bytes never change under its id. Shared caches may keep it, but not for so long that
# an unpublished lot's photos linger: a day, then revalidate.
PHOTO_CACHE = "public, max-age=86400"
DOCUMENT_CACHE = "public, max-age=3600"


@router.get(
    "/photos/{photo_id}/file",
    response_class=Response,
    responses={**NOT_FOUND, status.HTTP_200_OK: {"content": {"image/*": {}}}},
)
def public_photo(photo_id: UUID) -> Response:
    with public_session() as session:
        photo = session.get(LotPhoto, photo_id)
        if photo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        key, content_type = photo.storage_key, photo.content_type
    return Response(
        get_storage().get(key), media_type=content_type, headers={"Cache-Control": PHOTO_CACHE}
    )


@router.get(
    "/documents/{document_id}/file",
    response_class=Response,
    responses={**NOT_FOUND, status.HTTP_200_OK: {"content": {"application/pdf": {}}}},
)
def public_document(document_id: UUID) -> Response:
    with public_session() as session:
        document = session.get(LotDocument, document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        key, content_type = document.storage_key, document.content_type
        disposition = attachment(document.title, key.rsplit(".", 1)[-1])
    return Response(
        get_storage().get(key),
        media_type=content_type,
        headers={"Content-Disposition": disposition, "Cache-Control": DOCUMENT_CACHE},
    )
