"""Sign-in and sessions. Runs as cornerpin_auth (ADR-023)."""

from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from cornerpin.core.auth.events import MagicLinkRequested
from cornerpin.core.auth.tokens import hash_token, new_token, safe_next
from cornerpin.core.config import get_settings
from cornerpin.core.db import auth_session
from cornerpin.core.outbox import enqueue


@dataclass(frozen=True)
class SignedIn:
    user_id: UUID
    session_token: str
    next_path: str


def request_magic_link(email: str, next_path: str | None, *, engine: Engine | None = None) -> None:
    """Store a single-use token and queue the email in one transaction. Silently does nothing
    past the rate limit, so the response never reveals anything about the address."""
    settings = get_settings()
    with auth_session(engine=engine) as session:
        recent = session.execute(
            text(
                "SELECT count(*) FROM login_tokens"
                " WHERE email = :email AND created_at > now() - interval '15 minutes'"
            ),
            {"email": email},
        ).scalar_one()
        if recent >= settings.magic_links_per_15_minutes:
            return
        raw, digest = new_token()
        session.execute(
            text(
                "INSERT INTO login_tokens (token_hash, email, next_path, expires_at)"
                " VALUES (:hash, :email, :next,"
                " now() + make_interval(mins => :minutes))"
            ),
            {
                "hash": digest,
                "email": email,
                "next": safe_next(next_path),
                "minutes": settings.magic_link_minutes,
            },
        )
        url = f"{settings.web_origin}/auth/verify?{urlencode({'token': raw})}"
        enqueue(
            session,
            MagicLinkRequested(email=email, url=url, minutes_valid=settings.magic_link_minutes),
        )


def verify_magic_link(
    raw_token: str, user_agent: str | None, *, engine: Engine | None = None
) -> SignedIn | None:
    """Use the token (once), create the user on first sign-in, and start a session."""
    with auth_session(engine=engine) as session:
        row = session.execute(
            text(
                "UPDATE login_tokens SET used_at = now()"
                " WHERE token_hash = :hash AND used_at IS NULL AND expires_at > now()"
                " RETURNING email, next_path"
            ),
            {"hash": hash_token(raw_token)},
        ).one_or_none()
        if row is None:
            return None
        user_id = _verified_user(session, row.email, display_name=None)
        token = _start_session(session, user_id, user_agent)
        return SignedIn(user_id=user_id, session_token=token, next_path=row.next_path)


def sign_in_verified_email(
    email: str,
    display_name: str | None,
    next_path: str | None,
    user_agent: str | None,
    *,
    engine: Engine | None = None,
) -> SignedIn:
    """For an email address already verified by an identity provider (Google)."""
    with auth_session(engine=engine) as session:
        user_id = _verified_user(session, email, display_name=display_name)
        token = _start_session(session, user_id, user_agent)
        return SignedIn(user_id=user_id, session_token=token, next_path=safe_next(next_path))


def resolve_session(raw_token: str, *, engine: Engine | None = None) -> UUID | None:
    with auth_session(engine=engine) as session:
        params = {"hash": hash_token(raw_token)}
        session.execute(
            text(
                "UPDATE sessions SET last_seen_at = now() WHERE token_hash = :hash"
                " AND expires_at > now() AND last_seen_at < now() - interval '1 hour'"
            ),
            params,
        )
        user_id: UUID | None = session.execute(
            text("SELECT user_id FROM sessions WHERE token_hash = :hash AND expires_at > now()"),
            params,
        ).scalar_one_or_none()
        return user_id


def end_session(raw_token: str, *, engine: Engine | None = None) -> None:
    with auth_session(engine=engine) as session:
        session.execute(
            text("DELETE FROM sessions WHERE token_hash = :hash"),
            {"hash": hash_token(raw_token)},
        )


def _verified_user(session: Session, email: str, display_name: str | None) -> UUID:
    user_id: UUID = session.execute(
        text(
            "INSERT INTO users (email, display_name, email_verified_at)"
            " VALUES (:email, :name, now())"
            " ON CONFLICT (email) DO UPDATE"
            " SET email_verified_at = coalesce(users.email_verified_at, now())"
            " RETURNING id"
        ),
        {"email": email, "name": display_name},
    ).scalar_one()
    return user_id


def _start_session(session: Session, user_id: UUID, user_agent: str | None) -> str:
    raw, digest = new_token()
    session.execute(
        text(
            "INSERT INTO sessions (token_hash, user_id, expires_at, user_agent)"
            " VALUES (:hash, :user_id, now() + make_interval(days => :days), :agent)"
        ),
        {
            "hash": digest,
            "user_id": user_id,
            "days": get_settings().session_days,
            "agent": (user_agent or "")[:500] or None,
        },
    )
    return raw


def purge_expired(*, engine: Engine | None = None) -> tuple[int, int]:
    """Delete sign-in tokens and sessions that expired more than a day ago. Returns the counts
    (tokens, sessions)."""
    with auth_session(engine=engine) as session:
        tokens = session.execute(
            text(
                "DELETE FROM login_tokens WHERE expires_at < now() - interval '1 day' RETURNING id"
            )
        ).all()
        sessions = session.execute(
            text("DELETE FROM sessions WHERE expires_at < now() - interval '1 day' RETURNING id")
        ).all()
        return len(tokens), len(sessions)
