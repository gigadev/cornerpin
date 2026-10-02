"""Outbox handlers owned by the notifications module (ADR-029).

Handlers for things that happened (an inquiry, a lot change) fan out into one event per
recipient; the per-recipient handlers send. Everything is read again at send time, so nothing
goes out about a lot that has since been unpublished, and preferences changed in the meantime
are respected where they are checked.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.events import MagicLinkRequested
from cornerpin.core.config import get_settings
from cornerpin.core.directory import email_of, member_ids
from cornerpin.core.outbox import enqueue, handler
from cornerpin.leads import notices as leads
from cornerpin.leads.events import HoldRequested, InquiryReceived
from cornerpin.listings.events import LotChanged
from cornerpin.listings.notices import lot_notice
from cornerpin.notifications import messages
from cornerpin.notifications.email import Email, get_email_sender
from cornerpin.notifications.events import (
    OwnerHoldEmail,
    OwnerInquiryEmail,
    SavedLotEmail,
    SavedLotPush,
)
from cornerpin.notifications.prefs import prefs_of
from cornerpin.notifications.push import PushGone, PushTarget, get_push_sender


@handler(MagicLinkRequested, scrub=("url",))
def send_magic_link(event: MagicLinkRequested, _session: Session) -> None:
    get_email_sender().send(
        Email(
            to=event.email,
            subject="Your Cornerpin sign-in link",
            text=(
                "Use this link to sign in to Cornerpin:\n\n"
                f"{event.url}\n\n"
                f"It works once and expires in {event.minutes_valid} minutes. "
                "If you didn't ask for it, you can ignore this email.\n"
            ),
        )
    )


# --- owners: inquiries and hold requests ---------------------------------------------------


@handler(InquiryReceived)
def fan_out_inquiry(event: InquiryReceived, session: Session) -> None:
    inquiry = leads.inquiry(session, event.inquiry_id)
    if inquiry:
        for user_id in member_ids(session, inquiry.tenant_id):
            enqueue(session, OwnerInquiryEmail(inquiry_id=inquiry.id, user_id=user_id))


@handler(HoldRequested)
def fan_out_hold(event: HoldRequested, session: Session) -> None:
    hold = leads.hold_request(session, event.hold_request_id)
    if hold:
        for user_id in member_ids(session, hold.tenant_id):
            enqueue(session, OwnerHoldEmail(hold_request_id=hold.id, user_id=user_id))


def _email_owner(
    session: Session, kind: str, buyer: leads.BuyerMessage | None, user_id: UUID
) -> None:
    to = email_of(session, user_id)
    lot = lot_notice(session, buyer.lot_id) if buyer else None
    if buyer is None or to is None or lot is None:
        return  # deleted since; nothing to say
    message = messages.owner_email(kind, lot, buyer, buyer.tenant_id, get_settings().web_origin)
    get_email_sender().send(
        Email(to=to, subject=message.subject, text=message.text, reply_to=buyer.email)
    )


@handler(OwnerInquiryEmail)
def email_owner_inquiry(event: OwnerInquiryEmail, session: Session) -> None:
    _email_owner(session, "inquiry", leads.inquiry(session, event.inquiry_id), event.user_id)


@handler(OwnerHoldEmail)
def email_owner_hold(event: OwnerHoldEmail, session: Session) -> None:
    _email_owner(session, "hold", leads.hold_request(session, event.hold_request_id), event.user_id)


# --- savers: status and price changes ------------------------------------------------------


@handler(LotChanged)
def fan_out_lot_change(event: LotChanged, session: Session) -> None:
    """One email per saver who wants email, one push per subscription of savers who want
    push. Nothing while the lot isn't public: savers can't see it either."""
    lot = lot_notice(session, event.lot_id)
    if lot is None or not lot.public:
        return
    push_on = get_push_sender() is not None
    for user_id in leads.savers(session, lot.id):
        prefs = prefs_of(session, user_id)
        if prefs.email_saved_lot_changes:
            enqueue(session, SavedLotEmail(user_id=user_id, change=event))
        if push_on and prefs.push_saved_lot_changes:
            for subscription_id in session.execute(
                text("SELECT id FROM push_subscriptions WHERE user_id = :u"), {"u": user_id}
            ).scalars():
                enqueue(session, SavedLotPush(subscription_id=subscription_id, change=event))


@handler(SavedLotEmail)
def email_saver(event: SavedLotEmail, session: Session) -> None:
    to = email_of(session, event.user_id)
    lot = lot_notice(session, event.change.lot_id)
    if to is None or lot is None or not lot.public:
        return
    message = messages.lot_change_email(lot, event.change, get_settings().web_origin)
    get_email_sender().send(Email(to=to, subject=message.subject, text=message.text))


@handler(SavedLotPush)
def push_to_saver(event: SavedLotPush, session: Session) -> None:
    sender = get_push_sender()
    row = session.execute(
        text("SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE id = :id"),
        {"id": event.subscription_id},
    ).one_or_none()
    lot = lot_notice(session, event.change.lot_id)
    if sender is None or row is None or lot is None or not lot.public:
        return
    try:
        sender.send(
            PushTarget(endpoint=row.endpoint, p256dh=row.p256dh, auth=row.auth),
            messages.lot_change_push(lot, event.change, get_settings().web_origin),
        )
    except PushGone:
        session.execute(
            text("DELETE FROM push_subscriptions WHERE id = :id"), {"id": event.subscription_id}
        )
