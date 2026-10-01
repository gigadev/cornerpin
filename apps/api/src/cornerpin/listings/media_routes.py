"""Owner portal: a lot's photos and documents (P1-05). Files live in object storage behind
cornerpin.core.storage; rows in lot_media and lot_documents, under the same tenant RLS as lots.
Files are served through these routes, after the membership check."""

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.storage import get_storage, remove_later
from cornerpin.core.tenancy import tenant_session
from cornerpin.listings.media import (
    MAX_DOCUMENT_BYTES,
    MAX_PHOTO_BYTES,
    check_document,
    prepare_photo,
    read_limited,
)
from cornerpin.listings.models import DocumentKind, Lot, LotDocument, LotPhoto

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["media"])

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}
UPLOAD_ERRORS: Responses = {
    **NOT_FOUND,
    status.HTTP_413_CONTENT_TOO_LARGE: {"description": "File too large"},
}
# Owner-only, behind a session: browsers may keep it, shared caches may not. A photo's bytes
# never change under the same id.
PRIVATE_IMMUTABLE = "private, max-age=31536000, immutable"

Caption = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class PhotoOut(BaseModel):
    id: UUID
    caption: str
    sort_order: int
    width: int | None
    height: int | None
    content_type: str
    url: str


class PhotoUpdate(BaseModel):
    caption: Caption


class PhotoOrder(BaseModel):
    photo_ids: list[UUID] = Field(min_length=1)


class DocumentOut(BaseModel):
    id: UUID
    kind: DocumentKind
    title: str
    content_type: str
    size_bytes: int
    created_at: datetime
    url: str


def _lot(session: Session, lot_id: UUID) -> Lot:
    lot = session.get(Lot, lot_id)
    if lot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return lot


def _photo_out(tenant_id: UUID, photo: LotPhoto) -> PhotoOut:
    return PhotoOut(
        id=photo.id,
        caption=photo.caption,
        sort_order=photo.sort_order,
        width=photo.width,
        height=photo.height,
        content_type=photo.content_type,
        url=f"/v1/tenants/{tenant_id}/photos/{photo.id}/file",
    )


def _document_out(tenant_id: UUID, document: LotDocument) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        kind=document.kind,
        title=document.title,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        url=f"/v1/tenants/{tenant_id}/documents/{document.id}/file",
    )


def _photos(session: Session, tenant_id: UUID, lot_id: UUID) -> list[PhotoOut]:
    photos = session.scalars(
        select(LotPhoto)
        .where(LotPhoto.lot_id == lot_id)
        .order_by(LotPhoto.sort_order, LotPhoto.created_at)
    ).all()
    return [_photo_out(tenant_id, photo) for photo in photos]


def _store(session: Session, key: str, data: bytes, content_type: str, row: object) -> None:
    """Write the file, then the row; if the row fails, take the file back out."""
    storage = get_storage()
    storage.put(key, data, content_type)
    try:
        session.add(row)
        session.flush()
    except Exception:
        storage.delete(key)
        raise


# --- photos --------------------------------------------------------------------------------


@router.get("/lots/{lot_id}/photos", responses=NOT_FOUND)
def list_photos(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> list[PhotoOut]:
    with tenant_session(user, tenant_id) as session:
        _lot(session, lot_id)
        return _photos(session, tenant_id, lot_id)


@router.post("/lots/{lot_id}/photos", status_code=status.HTTP_201_CREATED, responses=UPLOAD_ERRORS)
async def upload_photo(
    tenant_id: UUID,
    lot_id: UUID,
    user: SignedInUser,
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP, up to 15 MB")],
    caption: Annotated[Caption, Form()] = "",
) -> PhotoOut:
    photo = prepare_photo(await read_limited(file, MAX_PHOTO_BYTES))
    with tenant_session(user, tenant_id) as session:
        _lot(session, lot_id)
        next_order = session.scalar(
            select(func.coalesce(func.max(LotPhoto.sort_order) + 1, 0)).where(
                LotPhoto.lot_id == lot_id
            )
        )
        photo_id = uuid4()
        row = LotPhoto(
            id=photo_id,
            tenant_id=tenant_id,
            lot_id=lot_id,
            storage_key=f"tenants/{tenant_id}/lots/{lot_id}/photos/{photo_id}.{photo.extension}",
            content_type=photo.content_type,
            caption=caption,
            sort_order=next_order or 0,
            width=photo.width,
            height=photo.height,
        )
        _store(session, row.storage_key, photo.data, photo.content_type, row)
        session.refresh(row)
        return _photo_out(tenant_id, row)


@router.patch("/photos/{photo_id}", responses=NOT_FOUND)
def update_photo(
    tenant_id: UUID, photo_id: UUID, body: PhotoUpdate, user: SignedInUser
) -> PhotoOut:
    with tenant_session(user, tenant_id) as session:
        photo = session.get(LotPhoto, photo_id)
        if photo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        photo.caption = body.caption
        session.flush()
        return _photo_out(tenant_id, photo)


@router.put(
    "/lots/{lot_id}/photos/order",
    responses={
        **NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Not exactly this lot's photos"},
    },
)
def reorder_photos(
    tenant_id: UUID, lot_id: UUID, body: PhotoOrder, user: SignedInUser
) -> list[PhotoOut]:
    """Set the order of all of a lot's photos at once; the list must name each exactly once."""
    with tenant_session(user, tenant_id) as session:
        _lot(session, lot_id)
        photos = {
            photo.id: photo
            for photo in session.scalars(select(LotPhoto).where(LotPhoto.lot_id == lot_id))
        }
        if len(body.photo_ids) != len(set(body.photo_ids)) or set(body.photo_ids) != set(photos):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "List each of this lot's photos once"
            )
        for position, photo_id in enumerate(body.photo_ids):
            photos[photo_id].sort_order = position
        session.flush()
        return _photos(session, tenant_id, lot_id)


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def delete_photo(tenant_id: UUID, photo_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        photo = session.get(LotPhoto, photo_id)
        if photo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        remove_later(session, photo.storage_key)
        session.delete(photo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/photos/{photo_id}/file",
    response_class=Response,
    responses={**NOT_FOUND, status.HTTP_200_OK: {"content": {"image/*": {}}}},
)
def photo_file(tenant_id: UUID, photo_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        photo = session.get(LotPhoto, photo_id)
        if photo is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        key, content_type = photo.storage_key, photo.content_type
    return Response(
        get_storage().get(key),
        media_type=content_type,
        headers={"Cache-Control": PRIVATE_IMMUTABLE},
    )


# --- documents -----------------------------------------------------------------------------


@router.get("/lots/{lot_id}/documents", responses=NOT_FOUND)
def list_documents(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> list[DocumentOut]:
    with tenant_session(user, tenant_id) as session:
        _lot(session, lot_id)
        documents = session.scalars(
            select(LotDocument)
            .where(LotDocument.lot_id == lot_id)
            .order_by(LotDocument.kind, LotDocument.title)
        ).all()
        return [_document_out(tenant_id, document) for document in documents]


@router.post(
    "/lots/{lot_id}/documents", status_code=status.HTTP_201_CREATED, responses=UPLOAD_ERRORS
)
async def upload_document(
    tenant_id: UUID,
    lot_id: UUID,
    user: SignedInUser,
    file: Annotated[UploadFile, File(description="PDF, JPEG or PNG, up to 25 MB")],
    kind: Annotated[DocumentKind, Form()],
    title: Annotated[Title, Form()],
) -> DocumentOut:
    document = check_document(await read_limited(file, MAX_DOCUMENT_BYTES))
    with tenant_session(user, tenant_id) as session:
        _lot(session, lot_id)
        document_id = uuid4()
        row = LotDocument(
            id=document_id,
            tenant_id=tenant_id,
            lot_id=lot_id,
            kind=kind,
            title=title,
            storage_key=(
                f"tenants/{tenant_id}/lots/{lot_id}/documents/{document_id}.{document.extension}"
            ),
            content_type=document.content_type,
            size_bytes=len(document.data),
        )
        _store(session, row.storage_key, document.data, document.content_type, row)
        session.refresh(row)
        return _document_out(tenant_id, row)


@router.delete(
    "/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND
)
def delete_document(tenant_id: UUID, document_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        document = session.get(LotDocument, document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        remove_later(session, document.storage_key)
        session.delete(document)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def attachment(title: str, extension: str) -> str:
    """Content-Disposition for a download named after the document's title."""
    name = f"{title}.{extension}"
    ascii_name = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in name
    )
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


@router.get(
    "/documents/{document_id}/file",
    response_class=Response,
    responses={**NOT_FOUND, status.HTTP_200_OK: {"content": {"application/pdf": {}}}},
)
def document_file(tenant_id: UUID, document_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        document = session.get(LotDocument, document_id)
        if document is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        key, content_type = document.storage_key, document.content_type
        disposition = attachment(document.title, key.rsplit(".", 1)[-1])
    return Response(
        get_storage().get(key),
        media_type=content_type,
        headers={"Content-Disposition": disposition, "Cache-Control": "private, no-store"},
    )
