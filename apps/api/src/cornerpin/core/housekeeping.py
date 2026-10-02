"""Periodic clean-up (ADR-029): spent sign-in tokens, expired sessions and old processed outbox
events. Locally the in-process runner calls it hourly; in the cloud Cloud Scheduler calls
/internal/housekeeping."""

import logging

from pydantic import BaseModel
from sqlalchemy import Engine

from cornerpin.core.auth.service import purge_expired
from cornerpin.core.outbox import purge_processed

log = logging.getLogger(__name__)


class HousekeepingResult(BaseModel):
    login_tokens: int
    sessions: int
    outbox_events: int


def run_housekeeping(*, engine: Engine | None = None) -> HousekeepingResult:
    tokens, sessions = purge_expired(engine=engine)
    result = HousekeepingResult(
        login_tokens=tokens, sessions=sessions, outbox_events=purge_processed(engine=engine)
    )
    log.info("housekeeping: %s", result)
    return result
