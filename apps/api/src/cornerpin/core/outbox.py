"""Transactional outbox (ADR-010, ADR-023).

Producers call `enqueue` inside the transaction that makes the change, so the event exists if
and only if the change committed. Handlers run later, as cornerpin_worker, with retries. Every
third-party call (email, and later Slack, Salesforce, Claude...) happens in a handler, never in
a request.

Locally `InProcessRunner` polls the table from the API process. P1-09 adds a Cloud Tasks
dispatcher that calls the same `process_pending`.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from cornerpin.core.db import worker_session

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 8


class Event(BaseModel):
    """An outbox event. Subclasses set `event_type`."""

    event_type: ClassVar[str]


@dataclass(frozen=True)
class _Handler:
    model: type[Event]
    handle: Callable[[Event], None]
    scrub: tuple[str, ...]


_handlers: dict[str, _Handler] = {}


def handler[E: Event](
    model: type[E], *, scrub: tuple[str, ...] = ()
) -> Callable[[Callable[[E], None]], Callable[[E], None]]:
    """Register the handler for an event type. `scrub` lists payload fields removed once the
    handler succeeds, for values that should not outlive their use (such as sign-in links)."""

    def register(fn: Callable[[E], None]) -> Callable[[E], None]:
        if model.event_type in _handlers:
            raise ValueError(f"duplicate handler for {model.event_type}")

        def handle(event: Event) -> None:
            fn(model.model_validate(event.model_dump()))

        _handlers[model.event_type] = _Handler(model=model, handle=handle, scrub=scrub)
        return fn

    return register


def enqueue(session: Session, event: Event) -> None:
    session.execute(
        text("INSERT INTO outbox (event_type, payload) VALUES (:type, CAST(:payload AS jsonb))"),
        {"type": event.event_type, "payload": event.model_dump_json()},
    )


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
                if entry is None:
                    raise LookupError(f"no handler for {row.event_type}")
                entry.handle(entry.model.model_validate(row.payload))
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
                {"id": row.id, "scrub": list(entry.scrub)},
            )
        return len(rows)


class InProcessRunner:
    """Polls the outbox on a background thread. Local development only (ADR-023)."""

    def __init__(self, interval_seconds: float = 1.0) -> None:
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="outbox-runner", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                while process_pending() and not self._stop.is_set():
                    pass
            except Exception:
                log.exception("outbox runner failed; retrying")
            self._stop.wait(self._interval)
