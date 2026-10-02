"""Owner portal: lot boundaries on the map, GeoJSON import and the plat overlay (P1-06,
ADR-026). Shapes are GeoJSON longitude/latitude in the API and MultiPolygon SRID 4326 in
PostGIS; acreage follows the boundary by trigger."""

import math
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.storage import get_storage, remove_later
from cornerpin.core.tenancy import constraint_errors, tenant_session
from cornerpin.listings.geometry import (
    FeatureCollection,
    MultiPolygonGeometry,
    PolygonGeometry,
    Shape,
    area_acres,
    as_geojson,
    check_shape,
    from_postgis,
    lot_number_of,
    overlapping_lots,
    to_postgis,
)
from cornerpin.listings.media import MAX_OVERLAY_EDGE, MAX_PHOTO_BYTES, prepare_photo, read_limited
from cornerpin.listings.models import (
    Lot,
    LotStatus,
    Phase,
    Subdivision,
    SubdivisionOverlay,
    lot_number_order,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["map"])

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}
METERS_PER_DEGREE_LAT = 111_132.0

LngLat = Annotated[list[float], Field(min_length=2, max_length=2)]
Corners = Annotated[list[LngLat], Field(min_length=4, max_length=4)]


class MapLot(BaseModel):
    id: UUID
    number: str
    status: LotStatus
    published: bool
    acreage: float | None
    boundary: MultiPolygonGeometry | None


class OverlayOut(BaseModel):
    url: str
    width: int
    height: int
    corners: Corners
    opacity: float


class SubdivisionMap(BaseModel):
    subdivision_id: UUID
    name: str
    center: LngLat
    lots: list[MapLot]
    overlay: OverlayOut | None


class BoundaryIn(BaseModel):
    boundary: Shape


class BoundaryOut(BaseModel):
    lot_id: UUID
    boundary: MultiPolygonGeometry | None
    acreage: float | None
    overlaps: list[str] = Field(description="Numbers of lots whose interiors overlap this one")


class ImportRequest(BaseModel):
    collection: FeatureCollection
    apply: bool = Field(default=False, description="False previews; true saves")
    phase_id: UUID | None = Field(
        default=None, description="Create lots that don't exist yet, in this phase"
    )


class ImportRow(BaseModel):
    index: int
    number: str | None
    action: Literal["update", "create", "skip"]
    reason: str | None = None
    lot_id: UUID | None = None
    acreage: float | None = None


class ImportReport(BaseModel):
    applied: bool
    rows: list[ImportRow]
    lots_without_shape: list[str] = Field(description="Lots in the subdivision the file missed")


class OverlayUpdate(BaseModel):
    corners: Corners | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)


def _subdivision(session: Session, subdivision_id: UUID) -> Subdivision:
    subdivision = session.get(Subdivision, subdivision_id)
    if subdivision is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return subdivision


def _overlay_out(tenant_id: UUID, overlay: SubdivisionOverlay) -> OverlayOut:
    return OverlayOut(
        url=f"/v1/tenants/{tenant_id}/subdivisions/{overlay.subdivision_id}/overlay/file",
        width=overlay.width,
        height=overlay.height,
        corners=overlay.corners,
        opacity=overlay.opacity,
    )


# --- map -----------------------------------------------------------------------------------


@router.get("/subdivisions/{subdivision_id}/map", responses=NOT_FOUND)
def subdivision_map(tenant_id: UUID, subdivision_id: UUID, user: SignedInUser) -> SubdivisionMap:
    """Everything the owner's map editor draws: all lots (published or not) and the overlay."""
    with tenant_session(user, tenant_id) as session:
        subdivision = _subdivision(session, subdivision_id)
        rows = session.execute(
            select(Lot, as_geojson(Lot.boundary))
            .where(Lot.subdivision_id == subdivision_id)
            .order_by(*lot_number_order())
        ).all()
        overlay = session.scalar(
            select(SubdivisionOverlay).where(SubdivisionOverlay.subdivision_id == subdivision_id)
        )
        return SubdivisionMap(
            subdivision_id=subdivision.id,
            name=subdivision.name,
            center=[subdivision.longitude, subdivision.latitude],
            lots=[
                MapLot(
                    id=lot.id,
                    number=lot.number,
                    status=lot.status,
                    published=lot.published,
                    acreage=float(lot.acreage) if lot.acreage is not None else None,
                    boundary=from_postgis(geojson),
                )
                for lot, geojson in rows
            ],
            overlay=_overlay_out(tenant_id, overlay) if overlay else None,
        )


# --- boundaries ----------------------------------------------------------------------------


def _boundary_out(session: Session, lot: Lot) -> BoundaryOut:
    session.flush()
    session.refresh(lot)
    geojson = session.scalar(select(as_geojson(Lot.boundary)).where(Lot.id == lot.id))
    return BoundaryOut(
        lot_id=lot.id,
        boundary=from_postgis(geojson),
        acreage=float(lot.acreage) if lot.acreage is not None else None,
        overlaps=overlapping_lots(session, lot.id, lot.subdivision_id),
    )


@router.put("/lots/{lot_id}/boundary", responses=NOT_FOUND)
def set_boundary(
    tenant_id: UUID, lot_id: UUID, body: BoundaryIn, user: SignedInUser
) -> BoundaryOut:
    """Save a lot's boundary. Acreage is recalculated from it; overlaps are reported."""
    with tenant_session(user, tenant_id) as session:
        lot = session.get(Lot, lot_id)
        if lot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        check_shape(session, body.boundary, lot.subdivision_id)
        lot.boundary = to_postgis(body.boundary)  # pyright: ignore[reportAttributeAccessIssue]
        return _boundary_out(session, lot)


@router.delete("/lots/{lot_id}/boundary", responses=NOT_FOUND)
def clear_boundary(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> BoundaryOut:
    """Remove a lot's boundary. Its last acreage stays and becomes editable again."""
    with tenant_session(user, tenant_id) as session:
        lot = session.get(Lot, lot_id)
        if lot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        lot.boundary = None
        return _boundary_out(session, lot)


# --- GeoJSON import ------------------------------------------------------------------------


def _shape_of(geometry: dict[str, JsonValue] | None) -> PolygonGeometry | MultiPolygonGeometry:
    if geometry is None or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("Not a polygon")
    if geometry["type"] == "Polygon":
        return PolygonGeometry.model_validate(geometry)
    return MultiPolygonGeometry.model_validate(geometry)


@router.post(
    "/subdivisions/{subdivision_id}/import",
    responses={
        **NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"description": "Not usable GeoJSON"},
    },
)
def import_geojson(
    tenant_id: UUID, subdivision_id: UUID, body: ImportRequest, user: SignedInUser
) -> ImportReport:
    """Match each GeoJSON feature to a lot by its number and set the lot's boundary. With
    `apply` false nothing is saved: the report previews what would happen. Unusable features
    are skipped with a reason; the rest still apply."""
    with tenant_session(user, tenant_id) as session:
        _subdivision(session, subdivision_id)
        if body.phase_id is not None:
            phase = session.get(Phase, body.phase_id)
            if phase is None or phase.subdivision_id != subdivision_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a phase of this subdivision"
                )
        lots = {
            lot.number: lot
            for lot in session.scalars(select(Lot).where(Lot.subdivision_id == subdivision_id))
        }
        seen: set[str] = set()
        rows: list[ImportRow] = []
        for index, feature in enumerate(body.collection.features):
            number = lot_number_of(feature.properties)
            row = ImportRow(index=index, number=number, action="skip")
            rows.append(row)
            if number is None:
                row.reason = "No lot number in its properties (looked for number, lot, name…)"
                continue
            if number in seen:
                row.reason = f"Lot {number} appears more than once in the file"
                continue
            seen.add(number)
            try:
                shape = _shape_of(feature.geometry)
            except ValueError as exc:
                row.reason = str(exc).splitlines()[0]
                continue
            try:
                # A savepoint, so a shape PostGIS rejects outright can't abort the import.
                with session.begin_nested():
                    check_shape(session, shape, subdivision_id)
            except HTTPException as exc:
                row.reason = str(exc.detail)
                continue
            except DBAPIError:
                row.reason = "PostGIS couldn't read that shape"
                continue
            row.acreage = area_acres(session, shape)
            lot = lots.get(number)
            if lot is None and body.phase_id is None:
                row.reason = f"No lot {number} here; choose a phase to create missing lots"
                continue
            row.action = "update" if lot else "create"
            if not body.apply:
                row.lot_id = lot.id if lot else None
                continue
            if lot is None:
                lot = Lot(
                    tenant_id=tenant_id,
                    subdivision_id=subdivision_id,
                    phase_id=body.phase_id,
                    number=number,
                )
                session.add(lot)
                lots[number] = lot
            lot.boundary = to_postgis(shape)  # pyright: ignore[reportAttributeAccessIssue]
            with constraint_errors({}):
                session.flush()
            row.lot_id = lot.id
        missing = sorted(set(lots) - seen, key=lambda n: (not n.isdigit(), n.zfill(16)))
        return ImportReport(applied=body.apply, rows=rows, lots_without_shape=missing)


# --- plat overlay --------------------------------------------------------------------------


def _default_corners(
    session: Session, subdivision: Subdivision, width: int, height: int
) -> list[list[float]]:
    """Centre the image over the drawn lots (or the subdivision's point), about as wide as
    them, keeping the image's proportions. The owner then drags the corners into place."""
    extent = session.execute(
        select(
            func.ST_XMin(func.ST_Extent(Lot.boundary)),
            func.ST_YMin(func.ST_Extent(Lot.boundary)),
            func.ST_XMax(func.ST_Extent(Lot.boundary)),
            func.ST_YMax(func.ST_Extent(Lot.boundary)),
        ).where(Lot.subdivision_id == subdivision.id)
    ).one()
    lng, lat = subdivision.longitude, subdivision.latitude
    meters_per_degree_lng = METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))
    width_m = 600.0
    if extent[0] is not None:
        west, south, east, north = (float(v) for v in extent)
        lng, lat = (west + east) / 2, (south + north) / 2
        width_m = max((east - west) * meters_per_degree_lng * 1.1, 100.0)
    height_m = width_m * height / width
    half_lng = width_m / 2 / meters_per_degree_lng
    half_lat = height_m / 2 / METERS_PER_DEGREE_LAT
    return [
        [lng - half_lng, lat + half_lat],
        [lng + half_lng, lat + half_lat],
        [lng + half_lng, lat - half_lat],
        [lng - half_lng, lat - half_lat],
    ]


def _overlay(session: Session, subdivision_id: UUID) -> SubdivisionOverlay:
    overlay = session.scalar(
        select(SubdivisionOverlay).where(SubdivisionOverlay.subdivision_id == subdivision_id)
    )
    if overlay is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No overlay")
    return overlay


@router.post(
    "/subdivisions/{subdivision_id}/overlay",
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, status.HTTP_413_CONTENT_TOO_LARGE: {"description": "Too large"}},
)
async def upload_overlay(
    tenant_id: UUID,
    subdivision_id: UUID,
    user: SignedInUser,
    file: Annotated[UploadFile, File(description="A plat image: JPEG, PNG or WebP")],
) -> OverlayOut:
    """Add the plat image, replacing any earlier one, placed roughly over the lots."""
    image = prepare_photo(await read_limited(file, MAX_PHOTO_BYTES), MAX_OVERLAY_EDGE)
    with tenant_session(user, tenant_id) as session:
        subdivision = _subdivision(session, subdivision_id)
        existing = session.scalar(
            select(SubdivisionOverlay).where(SubdivisionOverlay.subdivision_id == subdivision_id)
        )
        if existing is not None:
            remove_later(session, existing.storage_key)
            session.delete(existing)
            session.flush()
        overlay_id = uuid4()
        key = (
            f"tenants/{tenant_id}/subdivisions/{subdivision_id}"
            f"/overlay/{overlay_id}.{image.extension}"
        )
        get_storage().put(key, image.data, image.content_type)
        overlay = SubdivisionOverlay(
            id=overlay_id,
            tenant_id=tenant_id,
            subdivision_id=subdivision_id,
            storage_key=key,
            content_type=image.content_type,
            width=image.width,
            height=image.height,
            corners=_default_corners(session, subdivision, image.width, image.height),
        )
        session.add(overlay)
        try:
            session.flush()
        except Exception:
            get_storage().delete(key)
            raise
        session.refresh(overlay)
        return _overlay_out(tenant_id, overlay)


@router.patch("/subdivisions/{subdivision_id}/overlay", responses=NOT_FOUND)
def update_overlay(
    tenant_id: UUID, subdivision_id: UUID, body: OverlayUpdate, user: SignedInUser
) -> OverlayOut:
    """Save where the overlay's corners sit and how see-through it is."""
    with tenant_session(user, tenant_id) as session:
        overlay = _overlay(session, subdivision_id)
        if body.corners is not None:
            for lng, lat in body.corners:
                if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_CONTENT, "Corners must be longitude/latitude"
                    )
            overlay.corners = body.corners
        if body.opacity is not None:
            overlay.opacity = body.opacity
        session.flush()
        session.refresh(overlay)
        return _overlay_out(tenant_id, overlay)


@router.delete(
    "/subdivisions/{subdivision_id}/overlay",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
def delete_overlay(tenant_id: UUID, subdivision_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        overlay = _overlay(session, subdivision_id)
        remove_later(session, overlay.storage_key)
        session.delete(overlay)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/subdivisions/{subdivision_id}/overlay/file",
    response_class=Response,
    responses={**NOT_FOUND, status.HTTP_200_OK: {"content": {"image/*": {}}}},
)
def overlay_file(tenant_id: UUID, subdivision_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        overlay = _overlay(session, subdivision_id)
        key, content_type = overlay.storage_key, overlay.content_type
    # Replacing the overlay gives it a new key, but the URL stays the same, so don't cache long.
    return Response(
        get_storage().get(key),
        media_type=content_type,
        headers={"Cache-Control": "private, no-cache"},
    )
