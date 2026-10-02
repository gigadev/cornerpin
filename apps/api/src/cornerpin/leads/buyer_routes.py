"""Buyer activity (P1-08, ADR-028): saving lots, inquiries, hold requests and contact consent.

A lot is found through public_session first, so a buyer can only act on a lot the public can
see; the database checks the same thing again on insert (migration 0007). Anyone may send an
inquiry. Everything else, including giving contact consent, needs a signed-in (so verified)
email address.

Each inquiry and hold request queues an event in the same transaction; the owners' emails go
out from the outbox (P1-09).
"""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import CurrentUser, MaybeUser, SignedInUser
from cornerpin.core.auth.turnstile import TurnstileVerifier, client_ip, get_turnstile
from cornerpin.core.db import public_session, user_session
from cornerpin.core.outbox import enqueue
from cornerpin.leads import consent
from cornerpin.leads.events import HoldRequested, InquiryReceived
from cornerpin.leads.schemas import (
    BuyerLotState,
    ConsentChange,
    ConsentOut,
    ContactChoices,
    Created,
    HoldRequestCreate,
    InquiryCreate,
    SavedLot,
)
from cornerpin.listings.models import LotStatus

router = APIRouter(tags=["buyers"])

Responses = dict[int | str, dict[str, Any]]

NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "No such published lot"}}
INSUFFICIENT_PRIVILEGE = "42501"  # also what a failed row-level security check raises
UNIQUE_VIOLATION = "23505"


@dataclass(frozen=True)
class PublicLot:
    id: UUID
    tenant_id: UUID
    status: LotStatus


def _public_lot(lot_id: UUID) -> PublicLot:
    with public_session() as session:
        row = session.execute(
            text("SELECT id, tenant_id, status FROM lots WHERE id = :id"), {"id": lot_id}
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return PublicLot(id=row.id, tenant_id=row.tenant_id, status=LotStatus(row.status))


@contextmanager
def _lot_still_public() -> Generator[None]:
    """The insert policies refuse a lot that stopped being public since we looked it up."""
    try:
        yield
    except ProgrammingError as exc:
        if getattr(exc.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
        raise


@dataclass(frozen=True)
class Profile:
    email: str
    display_name: str | None
    phone: str | None


def _profile(session: Session, user_id: UUID) -> Profile:
    row = session.execute(
        text("SELECT email, display_name, phone FROM users WHERE id = :id"), {"id": user_id}
    ).one()
    return Profile(email=row.email, display_name=row.display_name, phone=row.phone)


def _fill_profile(session: Session, user_id: UUID, name: str, phone: str | None) -> Profile:
    """A form fills in the profile's name and phone where they are empty, and never overwrites
    them; the account page is where they change."""
    session.execute(
        text(
            "UPDATE users SET display_name = coalesce(display_name, :name),"
            " phone = coalesce(phone, :phone) WHERE id = :id"
        ),
        {"id": user_id, "name": name, "phone": phone},
    )
    return _profile(session, user_id)


def _record_contact(
    session: Session,
    lot: PublicLot,
    user: CurrentUser,
    profile: Profile,
    choices: ContactChoices | None,
    source: str,
) -> None:
    if choices is None:
        return
    if choices.sms and profile.phone is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a phone number to get text messages"
        )
    consent.record_choices(session, lot.tenant_id, user.id, choices, source)


# --- the lot page --------------------------------------------------------------------------


@router.get("/me/lots/{lot_id}", responses=NOT_FOUND)
def buyer_lot_state(lot_id: UUID, user: SignedInUser) -> BuyerLotState:
    lot = _public_lot(lot_id)
    with user_session(user.id) as session:
        profile = _profile(session, user.id)
        row = session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM saved_lots WHERE user_id = :u AND lot_id = :l)"
                " AS saved, EXISTS (SELECT 1 FROM hold_requests WHERE user_id = :u"
                " AND lot_id = :l AND status = 'pending') AS pending_hold"
            ),
            {"u": user.id, "l": lot.id},
        ).one()
        choices = consent.current_choices(session, lot.tenant_id, user.id)
    return BuyerLotState(
        saved=row.saved,
        pending_hold=row.pending_hold,
        contact=choices,
        email=profile.email,
        display_name=profile.display_name,
        phone=profile.phone,
    )


# --- saved lots ----------------------------------------------------------------------------


@router.get("/me/saved-lots")
def saved_lots(user: SignedInUser) -> list[SavedLot]:
    """Saved lots the public can still see, newest first. A lot that is unpublished drops out
    of the list but stays saved, and comes back if it is published again."""
    with user_session(user.id) as session:
        saved = {
            row.lot_id: row.created_at
            for row in session.execute(
                text("SELECT lot_id, created_at FROM saved_lots WHERE user_id = :u"),
                {"u": user.id},
            )
        }
    if not saved:
        return []
    with public_session() as session:
        rows = session.execute(
            text(
                "SELECT l.id, l.number, l.status, l.price, s.name, s.slug FROM lots l"
                " JOIN subdivisions s ON s.id = l.subdivision_id WHERE l.id = ANY(:ids)"
            ),
            {"ids": list(saved)},
        ).all()
    lots = [
        SavedLot(
            lot_id=row.id,
            number=row.number,
            status=LotStatus(row.status),
            price=None if row.price is None else int(row.price),
            subdivision_name=row.name,
            subdivision_slug=row.slug,
            saved_at=saved[row.id],
        )
        for row in rows
    ]
    return sorted(lots, key=lambda lot: lot.saved_at, reverse=True)


@router.put("/me/saved-lots/{lot_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND)
def save_lot(lot_id: UUID, user: SignedInUser) -> Response:
    lot = _public_lot(lot_id)
    with user_session(user.id) as session, _lot_still_public():
        session.execute(
            text(
                "INSERT INTO saved_lots (user_id, lot_id, tenant_id) VALUES (:u, :l, :t)"
                " ON CONFLICT DO NOTHING"
            ),
            {"u": user.id, "l": lot.id, "t": lot.tenant_id},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/saved-lots/{lot_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_lot(lot_id: UUID, user: SignedInUser) -> Response:
    """Works for any lot the buyer saved, published or not."""
    with user_session(user.id) as session:
        session.execute(
            text("DELETE FROM saved_lots WHERE user_id = :u AND lot_id = :l"),
            {"u": user.id, "l": lot_id},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- inquiries and hold requests -----------------------------------------------------------


@router.post(
    "/lots/{lot_id}/inquiries",
    status_code=status.HTTP_201_CREATED,
    responses={
        **NOT_FOUND,
        status.HTTP_400_BAD_REQUEST: {"description": "Turnstile check failed"},
    },
)
def create_inquiry(
    lot_id: UUID,
    body: InquiryCreate,
    request: Request,
    user: MaybeUser,
    turnstile: Annotated[TurnstileVerifier, Depends(get_turnstile)],
) -> Created:
    lot = _public_lot(lot_id)
    inquiry_id = uuid4()
    insert = text(
        "INSERT INTO inquiries (id, tenant_id, lot_id, user_id, name, email, phone, message)"
        " VALUES (:id, :t, :l, :u, :name, :email, :phone, :message)"
    )
    params = {
        "id": inquiry_id,
        "t": lot.tenant_id,
        "l": lot.id,
        "name": body.name,
        "phone": body.phone,
        "message": body.message,
    }

    if user is None:
        if body.contact is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Sign in to choose how we may contact you"
            )
        if body.email is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Enter your email")
        if not turnstile.verify(body.turnstile_token or "", client_ip(request)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turnstile check failed")
        # No RETURNING: the public role may insert an inquiry but never read one back.
        with public_session() as session, _lot_still_public():
            session.execute(insert, {**params, "u": None, "email": body.email})
            enqueue(session, InquiryReceived(inquiry_id=inquiry_id))
        return Created(id=inquiry_id)

    with user_session(user.id) as session, _lot_still_public():
        profile = _fill_profile(session, user.id, body.name, body.phone)
        session.execute(insert, {**params, "u": user.id, "email": profile.email})
        _record_contact(session, lot, user, profile, body.contact, "inquiry")
        enqueue(session, InquiryReceived(inquiry_id=inquiry_id))
    return Created(id=inquiry_id)


@router.post(
    "/lots/{lot_id}/hold-requests",
    status_code=status.HTTP_201_CREATED,
    responses={
        **NOT_FOUND,
        status.HTTP_409_CONFLICT: {"description": "Not available, or already requested"},
    },
)
def create_hold_request(lot_id: UUID, body: HoldRequestCreate, user: SignedInUser) -> Created:
    lot = _public_lot(lot_id)
    if lot.status != LotStatus.AVAILABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an available lot can be held")
    hold_id = uuid4()
    try:
        with user_session(user.id) as session, _lot_still_public():
            profile = _fill_profile(session, user.id, body.name, body.phone)
            session.execute(
                text(
                    "INSERT INTO hold_requests (id, tenant_id, lot_id, user_id, name, email,"
                    " phone, message) VALUES (:id, :t, :l, :u, :name, :email, :phone, :message)"
                ),
                {
                    "id": hold_id,
                    "t": lot.tenant_id,
                    "l": lot.id,
                    "u": user.id,
                    "name": body.name,
                    "email": profile.email,
                    "phone": body.phone,
                    "message": body.message,
                },
            )
            _record_contact(session, lot, user, profile, body.contact, "hold_request")
            enqueue(session, HoldRequested(hold_request_id=hold_id))
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "You've already asked to hold this lot"
            ) from exc
        raise
    return Created(id=hold_id)


# --- contact consent -----------------------------------------------------------------------


@router.get("/me/consents")
def my_consents(user: SignedInUser) -> list[ConsentOut]:
    """The current answer for each owner and channel the buyer has ever answered."""
    with user_session(user.id) as session:
        rows = session.execute(
            text(
                "SELECT DISTINCT ON (c.tenant_id, c.channel) c.tenant_id, t.name AS tenant_name,"
                " c.channel::text AS channel, c.granted, c.source, c.recorded_at"
                " FROM contact_consents c JOIN tenants t ON t.id = c.tenant_id"
                " WHERE c.user_id = :u"
                " ORDER BY c.tenant_id, c.channel, c.recorded_at DESC"
            ),
            {"u": user.id},
        ).all()
    consents = [ConsentOut.model_validate(row, from_attributes=True) for row in rows]
    return sorted(consents, key=lambda c: (c.tenant_name, c.channel))


@router.post(
    "/me/consents",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={status.HTTP_404_NOT_FOUND: {"description": "No earlier answer for that owner"}},
)
def change_consent(body: ConsentChange, user: SignedInUser) -> Response:
    """Change an earlier answer. Only owners the buyer has already answered appear on the
    account page, so a first answer always comes from a lot page."""
    with user_session(user.id) as session:
        known = session.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM contact_consents"
                " WHERE user_id = :u AND tenant_id = :t)"
            ),
            {"u": user.id, "t": body.tenant_id},
        ).scalar_one()
        if not known:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        if body.channel == "sms" and body.granted and _profile(session, user.id).phone is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a phone number to get text messages"
            )
        consent.record(session, body.tenant_id, user.id, body.channel, body.granted, "account")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
