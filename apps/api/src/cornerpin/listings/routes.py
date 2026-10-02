"""Owner portal: subdivisions, phases and lots for one tenant (P1-04). Every query runs in a
tenant_session, so RLS limits it to the tenant in the path, and only if the user is a member.
Status and price history is written by the database trigger, not here."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import Function

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.storage import remove_later
from cornerpin.core.tenancy import constraint_errors, tenant_session
from cornerpin.listings.models import (
    ListingType,
    Lot,
    LotDocument,
    LotPhoto,
    LotPriceChange,
    LotStatus,
    LotStatusChange,
    Phase,
    Subdivision,
    SubdivisionOverlay,
    lot_number_order,
)
from cornerpin.listings.schemas import (
    Home,
    LotCreate,
    LotDetail,
    LotSummary,
    LotUpdate,
    PhaseCreate,
    PhaseOut,
    PhaseUpdate,
    PriceChange,
    StatusChange,
    SubdivisionCreate,
    SubdivisionDetail,
    SubdivisionSummary,
    SubdivisionUpdate,
)

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["listings"])

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}
CONFLICT: Responses = {status.HTTP_409_CONFLICT: {"description": "Duplicate, or still in use"}}

BUYER_ACTIVITY = "This lot has inquiries or hold requests, so it can't be deleted. Unpublish it."

MESSAGES = {
    "subdivisions_slug_key": "That web address is already taken",
    "subdivisions_slug_check": "That web address is reserved or malformed",
    "subdivisions_slug_check1": "That web address is reserved or malformed",
    "lots_subdivision_id_number_key": "A lot with that number already exists here",
    "lots_phase_id_subdivision_id_fkey": "That phase belongs to a different subdivision",
}


def _point(latitude: float, longitude: float) -> Function[Any]:
    return func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326)


def _dollars(value: Decimal | None) -> int | None:
    return None if value is None else int(value)


def _get[T](session: Session, model: type[T], id_: UUID) -> T:
    found = session.get(model, id_)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return found


# --- subdivisions --------------------------------------------------------------------------


@router.get("/subdivisions", responses=NOT_FOUND)
def list_subdivisions(tenant_id: UUID, user: SignedInUser) -> list[SubdivisionSummary]:
    with tenant_session(user, tenant_id) as session:
        lot_count = func.count(Lot.id)
        available = func.count(Lot.id).filter(Lot.status == LotStatus.AVAILABLE)
        rows = session.execute(
            select(Subdivision, lot_count, available)
            .outerjoin(Lot, Lot.subdivision_id == Subdivision.id)
            .group_by(Subdivision.id)
            .order_by(Subdivision.name)
        ).all()
        return [
            SubdivisionSummary(
                id=sub.id,
                name=sub.name,
                slug=sub.slug,
                time_zone=sub.time_zone,
                published=sub.published,
                lot_count=total,
                available_count=free,
            )
            for sub, total, free in rows
        ]


@router.post(
    "/subdivisions",
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
)
def create_subdivision(
    tenant_id: UUID, body: SubdivisionCreate, user: SignedInUser
) -> SubdivisionDetail:
    with tenant_session(user, tenant_id) as session:
        subdivision = Subdivision(
            tenant_id=tenant_id,
            name=body.name,
            slug=body.slug,
            time_zone=body.time_zone,
            description=body.description,
            published=body.published,
            location=_point(body.latitude, body.longitude),
        )
        session.add(subdivision)
        with constraint_errors(MESSAGES):
            session.flush()
        return _subdivision_detail(session, subdivision.id)


@router.get("/subdivisions/{subdivision_id}", responses=NOT_FOUND)
def get_subdivision(tenant_id: UUID, subdivision_id: UUID, user: SignedInUser) -> SubdivisionDetail:
    with tenant_session(user, tenant_id) as session:
        return _subdivision_detail(session, subdivision_id)


@router.patch("/subdivisions/{subdivision_id}", responses={**NOT_FOUND, **CONFLICT})
def update_subdivision(
    tenant_id: UUID, subdivision_id: UUID, body: SubdivisionUpdate, user: SignedInUser
) -> SubdivisionDetail:
    with tenant_session(user, tenant_id) as session:
        subdivision = _get(session, Subdivision, subdivision_id)
        changes = body.model_dump(exclude_unset=True, exclude={"latitude", "longitude"})
        for field, value in changes.items():
            if value is not None:
                setattr(subdivision, field, value)
        if body.latitude is not None and body.longitude is not None:
            subdivision.location = _point(body.latitude, body.longitude)
        with constraint_errors(MESSAGES):
            session.flush()
        session.expire(subdivision)
        return _subdivision_detail(session, subdivision_id)


@router.delete(
    "/subdivisions/{subdivision_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_subdivision(tenant_id: UUID, subdivision_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        subdivision = _get(session, Subdivision, subdivision_id)
        lots = session.scalar(select(func.count()).where(Lot.subdivision_id == subdivision_id))
        if lots:
            raise HTTPException(status.HTTP_409_CONFLICT, "Delete or move its lots first")
        overlay_key = session.scalar(
            select(SubdivisionOverlay.storage_key).where(
                SubdivisionOverlay.subdivision_id == subdivision_id
            )
        )
        if overlay_key:
            remove_later(session, overlay_key)
        session.delete(subdivision)  # its phases and overlay go with it
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _subdivision_detail(session: Session, subdivision_id: UUID) -> SubdivisionDetail:
    subdivision = _get(session, Subdivision, subdivision_id)
    lot_counts: dict[UUID, int] = {
        phase_id: count
        for phase_id, count in session.execute(
            select(Lot.phase_id, func.count())
            .where(Lot.subdivision_id == subdivision_id)
            .group_by(Lot.phase_id)
        )
    }
    phases = session.scalars(
        select(Phase)
        .where(Phase.subdivision_id == subdivision_id)
        .order_by(Phase.sort_order, Phase.name)
    ).all()
    phase_names = {phase.id: phase.name for phase in phases}
    lots = session.scalars(
        select(Lot).where(Lot.subdivision_id == subdivision_id).order_by(*lot_number_order())
    ).all()
    return SubdivisionDetail(
        id=subdivision.id,
        name=subdivision.name,
        slug=subdivision.slug,
        time_zone=subdivision.time_zone,
        latitude=subdivision.latitude,
        longitude=subdivision.longitude,
        description=subdivision.description,
        published=subdivision.published,
        phases=[
            PhaseOut(
                id=phase.id,
                name=phase.name,
                sort_order=phase.sort_order,
                release_status=phase.release_status,
                lot_count=lot_counts.get(phase.id, 0),
            )
            for phase in phases
        ],
        lots=[
            LotSummary(
                id=lot.id,
                number=lot.number,
                phase_id=lot.phase_id,
                phase_name=phase_names.get(lot.phase_id, ""),
                status=lot.status,
                listing_type=lot.listing_type,
                price=_dollars(lot.price),
                acreage=float(lot.acreage) if lot.acreage is not None else None,
                published=lot.published,
            )
            for lot in lots
        ],
    )


# --- phases --------------------------------------------------------------------------------


def _phase_out(session: Session, phase: Phase) -> PhaseOut:
    lots = session.scalar(select(func.count()).where(Lot.phase_id == phase.id)) or 0
    return PhaseOut(
        id=phase.id,
        name=phase.name,
        sort_order=phase.sort_order,
        release_status=phase.release_status,
        lot_count=lots,
    )


@router.post(
    "/subdivisions/{subdivision_id}/phases",
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
)
def create_phase(
    tenant_id: UUID, subdivision_id: UUID, body: PhaseCreate, user: SignedInUser
) -> PhaseOut:
    with tenant_session(user, tenant_id) as session:
        _get(session, Subdivision, subdivision_id)
        phase = Phase(tenant_id=tenant_id, subdivision_id=subdivision_id, **body.model_dump())
        session.add(phase)
        session.flush()
        session.refresh(phase)
        return _phase_out(session, phase)


@router.patch("/phases/{phase_id}", responses=NOT_FOUND)
def update_phase(
    tenant_id: UUID, phase_id: UUID, body: PhaseUpdate, user: SignedInUser
) -> PhaseOut:
    with tenant_session(user, tenant_id) as session:
        phase = _get(session, Phase, phase_id)
        for field, value in body.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(phase, field, value)
        session.flush()
        session.refresh(phase)
        return _phase_out(session, phase)


@router.delete(
    "/phases/{phase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_phase(tenant_id: UUID, phase_id: UUID, user: SignedInUser) -> Response:
    with tenant_session(user, tenant_id) as session:
        phase = _get(session, Phase, phase_id)
        if session.scalar(select(func.count()).where(Lot.phase_id == phase_id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Delete or move its lots first")
        session.delete(phase)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- lots ----------------------------------------------------------------------------------


def _apply_home(lot: Lot, home: Home | None) -> None:
    lot.home_bedrooms = home.bedrooms if home else None
    lot.home_bathrooms = (
        Decimal(str(home.bathrooms)) if home and home.bathrooms is not None else None
    )
    lot.home_square_feet = home.square_feet if home else None
    lot.home_description = home.description if home else None


def _require_phase_in(session: Session, phase_id: UUID, subdivision_id: UUID) -> None:
    phase = session.get(Phase, phase_id)
    if phase is None or phase.subdivision_id != subdivision_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose a phase of this subdivision"
        )


@router.post(
    "/subdivisions/{subdivision_id}/lots",
    status_code=status.HTTP_201_CREATED,
    responses={**NOT_FOUND, **CONFLICT},
)
def create_lot(
    tenant_id: UUID, subdivision_id: UUID, body: LotCreate, user: SignedInUser
) -> LotDetail:
    with tenant_session(user, tenant_id) as session:
        _get(session, Subdivision, subdivision_id)
        _require_phase_in(session, body.phase_id, subdivision_id)
        lot = Lot(
            tenant_id=tenant_id,
            subdivision_id=subdivision_id,
            phase_id=body.phase_id,
            number=body.number,
            acreage=Decimal(str(body.acreage)) if body.acreage is not None else None,
            price=Decimal(body.price) if body.price is not None else None,
            status=body.status,
            listing_type=body.listing_type,
            published=body.published,
        )
        _apply_home(lot, body.home)
        session.add(lot)
        with constraint_errors(MESSAGES):
            session.flush()
        return _lot_detail(session, lot.id)


@router.get("/lots/{lot_id}", responses=NOT_FOUND)
def get_lot(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> LotDetail:
    with tenant_session(user, tenant_id) as session:
        return _lot_detail(session, lot_id)


@router.patch("/lots/{lot_id}", responses={**NOT_FOUND, **CONFLICT})
def update_lot(tenant_id: UUID, lot_id: UUID, body: LotUpdate, user: SignedInUser) -> LotDetail:
    with tenant_session(user, tenant_id) as session:
        lot = _get(session, Lot, lot_id)
        sent = body.model_fields_set
        if body.number is not None:
            lot.number = body.number
        if body.phase_id is not None:
            _require_phase_in(session, body.phase_id, lot.subdivision_id)
            lot.phase_id = body.phase_id
        if "acreage" in sent:
            lot.acreage = Decimal(str(body.acreage)) if body.acreage is not None else None
        if "price" in sent:
            lot.price = Decimal(body.price) if body.price is not None else None
        if body.status is not None:
            lot.status = body.status
        if body.listing_type is not None:
            lot.listing_type = body.listing_type
        if lot.listing_type == ListingType.LAND_ONLY:
            if "home" in sent and body.home is not None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "A land-only lot has no home details"
                )
            _apply_home(lot, None)
        elif "home" in sent:
            _apply_home(lot, body.home)
        if body.published is not None:
            lot.published = body.published
        with constraint_errors(MESSAGES):
            session.flush()
        session.expire(lot)
        return _lot_detail(session, lot_id)


@router.delete(
    "/lots/{lot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**NOT_FOUND, **CONFLICT},
)
def delete_lot(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> Response:
    """Refused (409) while the lot has inquiries or hold requests; the database enforces it."""
    with tenant_session(user, tenant_id) as session:
        lot = _get(session, Lot, lot_id)
        # Its photos and documents go with it; their files are removed once this commits.
        for key in session.scalars(
            select(LotPhoto.storage_key)
            .where(LotPhoto.lot_id == lot_id)
            .union_all(select(LotDocument.storage_key).where(LotDocument.lot_id == lot_id))
        ):
            remove_later(session, key)
        session.delete(lot)
        with constraint_errors(
            {
                "inquiries_lot_id_tenant_id_fkey": BUYER_ACTIVITY,
                "hold_requests_lot_id_tenant_id_fkey": BUYER_ACTIVITY,
            },
            foreign_key_status=status.HTTP_409_CONFLICT,
        ):
            session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _lot_detail(session: Session, lot_id: UUID) -> LotDetail:
    lot = _get(session, Lot, lot_id)
    subdivision = _get(session, Subdivision, lot.subdivision_id)
    statuses = session.scalars(
        select(LotStatusChange)
        .where(LotStatusChange.lot_id == lot_id)
        .order_by(LotStatusChange.changed_at.desc(), LotStatusChange.from_status.is_(None))
    ).all()
    prices = session.scalars(
        select(LotPriceChange)
        .where(LotPriceChange.lot_id == lot_id)
        .order_by(LotPriceChange.changed_at.desc(), LotPriceChange.from_price.is_(None))
    ).all()
    has_home = lot.listing_type == ListingType.LOT_AND_HOME
    return LotDetail(
        id=lot.id,
        subdivision_id=lot.subdivision_id,
        subdivision_name=subdivision.name,
        time_zone=subdivision.time_zone,
        phase_id=lot.phase_id,
        number=lot.number,
        acreage=float(lot.acreage) if lot.acreage is not None else None,
        price=_dollars(lot.price),
        status=lot.status,
        listing_type=lot.listing_type,
        home=Home(
            bedrooms=lot.home_bedrooms,
            bathrooms=float(lot.home_bathrooms) if lot.home_bathrooms is not None else None,
            square_feet=lot.home_square_feet,
            description=lot.home_description,
        )
        if has_home
        else None,
        published=lot.published,
        updated_at=lot.updated_at,
        status_history=[
            StatusChange(
                from_status=change.from_status,
                to_status=change.to_status,
                changed_by_email=change.changed_by_email,
                changed_at=change.changed_at,
            )
            for change in statuses
        ],
        price_history=[
            PriceChange(
                from_price=_dollars(change.from_price),
                to_price=_dollars(change.to_price),
                changed_by_email=change.changed_by_email,
                changed_at=change.changed_at,
            )
            for change in prices
        ],
    )
