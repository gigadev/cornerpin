"""Transactional outbox (ADR-010, ADR-023, ADR-029).

Producers call `enqueue` inside the transaction that makes the change, so the event exists if
and only if the change committed. A few events are queued by database triggers instead (a
lot's status or price changing). Handlers run later, as cornerpin_worker, with retries. Every
third-party call (email, push, and later Slack, Salesforce, Claude...) happens in a handler,
never in a request.

Each event is handled inside its own savepoint, with the worker's session, so a handler can
read what it needs and queue follow-up events: one event per recipient, so a retry never
repeats a send that already succeeded. A handler that fails leaves nothing behind.

After a commit that queued events, the dispatcher is told: locally the in-process runner wakes;
in the cloud a Cloud Task calls /internal/outbox/drain. Each cloud drain then books the next
one for when the next waiting event is due (a delayed send, a retry), ADR-043. A scheduled
drain catches anything a notification missed; code that may fire a queuing trigger calls
`expect_events`.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Protocol

from pydantic import BaseModel
from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from cornerpin.core.db import worker_session

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
PROCESSED_KEEP_DAYS = 30
_PENDING_FLAG = "outbox_pending"


class Event(BaseModel):
    """An outbox event. Subclasses set `event_type`."""

    event_type: ClassVar[str]


@dataclass(frozen=True)
class _Handler:
    model: type[Event]
    handle: Callable[[Event, Session], None]
    scrub: tuple[str, ...]


_handlers: dict[str, _Handler] = {}


def handler[E: Event](
    model: type[E], *, scrub: tuple[str, ...] = ()
) -> Callable[[Callable[[E, Session], None]], Callable[[E, Session], None]]:
    """Register the handler for an event type. It gets the event and the worker's session.
    `scrub` lists payload fields removed once the handler succeeds, for values that should not
    outlive their use (such as sign-in links)."""

    def register(fn: Callable[[E, Session], None]) -> Callable[[E, Session], None]:
        if model.event_type in _handlers:
            raise ValueError(f"duplicate handler for {model.event_type}")

        def handle(event: Event, session: Session) -> None:
            fn(model.model_validate(event.model_dump()), session)

        _handlers[model.event_type] = _Handler(model=model, handle=handle, scrub=scrub)
        return fn

    return register


def enqueue(session: Session, event: Event, *, available_at: datetime | None = None) -> None:
    """Queue `event` in this transaction; with `available_at`, not before then."""
    session.execute(
        text(
            "INSERT INTO outbox (event_type, payload, available_at)"
            " VALUES (:type, CAST(:payload AS jsonb), coalesce(:at, now()))"
        ),
        {"type": event.event_type, "payload": event.model_dump_json(), "at": available_at},
    )
    expect_events(session)


def expect_events(session: Session) -> None:
    """Tell the dispatcher after this transaction commits, for events a database trigger
    queues (a lot's status or price changing) that Python never sees."""
    session.info[_PENDING_FLAG] = True


def process_pending(*, limit: int = 20, engine: Engine | None = None) -> int:
    """Handle up to `limit` due events. Returns how many were attempted."""
    with worker_session(engine=engine) as session:
        rows = session.execute(
            text(
                "SELECT id, event_type, payload, attempts FROM outbox"
                " WHERE processed_at IS NULL AND available_at <= now() AND attempts < :max"
                " ORDER BY id LIMIT :limit FOR UPDATE SKIP LOCKED"
            ),
            {"max": MAX_ATTEMPTS, "limit": limit},
        ).all()
        for row in rows:
            entry = _handlers.get(row.event_type)
            try:
                with session.begin_nested():
                    if entry is None:
                        raise LookupError(f"no handler for {row.event_type}")
                    entry.handle(entry.model.model_validate(row.payload), session)
            except Exception as exc:
                log.warning("outbox event %s (%s) failed: %s", row.id, row.event_type, exc)
                session.execute(
                    text(
                        "UPDATE outbox SET attempts = attempts + 1, last_error = :error,"
                        " available_at = now() + make_interval(secs => :delay) WHERE id = :id"
                    ),
                    {"id": row.id, "error": str(exc)[:2000], "delay": min(2**row.attempts, 3600)},
                )
                continue
            session.execute(
                text(
                    "UPDATE outbox SET processed_at = now(), attempts = attempts + 1,"
                    " last_error = NULL, payload = payload - CAST(:scrub AS text[])"
                    " WHERE id = :id"
                ),
                {"id": row.id, "scrub": list(entry.scrub) if entry else []},
            )
        return len(rows)


def drain(*, max_batches: int = 50, engine: Engine | None = None) -> int:
    """Process due events until none are left (or `max_batches` ran). Returns the count."""
    total = 0
    for _ in range(max_batches):
        attempted = process_pending(engine=engine)
        total += attempted
        if attempted == 0:
            break
    return total


def next_due(*, engine: Engine | None = None) -> datetime | None:
    """When the earliest event still waiting is due: in the future for a delayed send or a
    retry's back-off, in the past if a drain stopped with work left. None if nothing waits."""
    with worker_session(engine=engine) as session:
        return session.execute(
            text(
                "SELECT min(available_at) FROM outbox"
                " WHERE processed_at IS NULL AND attempts < :max"
            ),
            {"max": MAX_ATTEMPTS},
        ).scalar_one()


def schedule_next(*, engine: Engine | None = None) -> datetime | None:
    """Ask the dispatcher to come back when the next waiting event is due. Returns that time."""
    when = next_due(engine=engine)
    if when is not None:
        try:
            _dispatcher.notify_at(when)
        except Exception:
            # The scheduled drain will pick it up instead, just later.
            log.exception("could not schedule the next outbox drain")
    return when


def purge_processed(*, engine: Engine | None = None) -> int:
    """Delete events processed more than PROCESSED_KEEP_DAYS ago. Failed events stay, so
    they can be looked at."""
    with worker_session(engine=engine) as session:
        removed = session.execute(
            text(
                "DELETE FROM outbox WHERE processed_at < now() - make_interval(days => :days)"
                " RETURNING id"
            ),
            {"days": PROCESSED_KEEP_DAYS},
        ).all()
        return len(removed)


# --- dispatch ------------------------------------------------------------------------------


class Dispatcher(Protocol):
    def notify(self) -> None:
        """Events were committed; arrange for them to be processed soon."""
        ...

    def notify_at(self, when: datetime) -> None:
        """An event waits until `when`; arrange for it to be processed then."""
        ...


class _NoDispatch:
    def notify(self) -> None:
        pass

    def notify_at(self, when: datetime) -> None:
        pass


_dispatcher: Dispatcher = _NoDispatch()


def set_dispatcher(dispatcher: Dispatcher | None) -> None:
    global _dispatcher
    _dispatcher = dispatcher or _NoDispatch()


@event.listens_for(Session, "after_commit")
def _notify_after_commit(session: Session) -> None:
    if session.info.pop(_PENDING_FLAG, False):
        try:
            _dispatcher.notify()
        except Exception:
            # The change is committed; the scheduled drain will pick the events up.
            log.exception("could not dispatch outbox events")


@event.listens_for(Session, "after_rollback")
def _forget_after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_FLAG, None)


class InProcessRunner:
    """Polls the outbox on a background thread, and wakes early when told events were
    committed. Also runs `hourly` (housekeeping) once an hour. Local development only
    (ADR-023)."""

    def __init__(
        self, interval_seconds: float = 1.0, hourly: Callable[[], object] | None = None
    ) -> None:
        self._interval = interval_seconds
        self._hourly = hourly
        self._next_hourly = 0.0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._run, name="outbox-runner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=5)

    def notify(self) -> None:
        self._wake.set()

    def notify_at(self, when: datetime) -> None:
        pass  # it polls every interval anyway

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.clear()
            try:
                drain()
                if self._hourly and time.monotonic() >= self._next_hourly:
                    self._next_hourly = time.monotonic() + 3600
                    self._hourly()
            except Exception:
                log.exception("outbox runner failed; retrying")
            self._wake.wait(self._interval)
