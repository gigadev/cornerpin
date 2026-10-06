"""Outbox handlers for outreach (ADR-036). Importing this module registers them."""

from sqlalchemy.orm import Session

from cornerpin.core.outbox import handler
from cornerpin.outreach import policy
from cornerpin.outreach.events import OutreachSend
from cornerpin.outreach.service import deliver


@handler(OutreachSend)
def send_outreach(event: OutreachSend, session: Session) -> None:
    deliver(session, event.message_id, policy.utcnow())
