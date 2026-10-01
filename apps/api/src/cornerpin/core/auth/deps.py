from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Response, status

from cornerpin.core.auth.service import resolve_session
from cornerpin.core.config import get_settings

SESSION_COOKIE = "cp_session"


@dataclass(frozen=True)
class CurrentUser:
    id: UUID


def current_user(cp_session: Annotated[str | None, Cookie()] = None) -> CurrentUser:
    """The signed-in user from the session cookie; 401 otherwise."""
    user_id = resolve_session(cp_session) if cp_session else None
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    return CurrentUser(id=user_id)


SignedInUser = Annotated[CurrentUser, Depends(current_user)]


def secure_cookies() -> bool:
    return get_settings().web_origin.startswith("https://")


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_settings().session_days * 86_400,
        httponly=True,
        secure=secure_cookies(),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=secure_cookies(), samesite="lax", path="/"
    )
