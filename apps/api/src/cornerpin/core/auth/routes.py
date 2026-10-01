import secrets
from typing import Annotated

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import AfterValidator, BaseModel, Field

from cornerpin.core.auth import service
from cornerpin.core.auth.deps import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from cornerpin.core.auth.google import GoogleSignIn, get_google
from cornerpin.core.auth.tokens import safe_next, sign, unsign
from cornerpin.core.auth.turnstile import TurnstileVerifier, get_turnstile
from cornerpin.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_COOKIE = "cp_oauth"
OAUTH_COOKIE_PATH = "/v1/auth/google"
OAUTH_MAX_AGE_SECONDS = 600


def _email_address(value: str) -> str:
    """Normalized address. Locally .test domains are allowed, so Mailpit can receive them."""
    try:
        return validate_email(
            value, check_deliverability=False, test_environment=get_settings().is_local
        ).normalized
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc


EmailAddress = Annotated[
    str, AfterValidator(_email_address), Field(json_schema_extra={"format": "email"})
]


class AuthProviders(BaseModel):
    turnstile_site_key: str
    google: bool


class MagicLinkRequest(BaseModel):
    email: EmailAddress
    turnstile_token: str
    next: str | None = None


class MagicLinkSent(BaseModel):
    status: str = "sent"


class MagicLinkVerify(BaseModel):
    token: str


class SignInResult(BaseModel):
    next: str


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/providers")
def providers(google: Annotated[GoogleSignIn | None, Depends(get_google)]) -> AuthProviders:
    return AuthProviders(
        turnstile_site_key=get_settings().turnstile_site_key, google=google is not None
    )


@router.post("/magic-link", status_code=status.HTTP_202_ACCEPTED)
def request_magic_link(
    body: MagicLinkRequest,
    request: Request,
    turnstile: Annotated[TurnstileVerifier, Depends(get_turnstile)],
) -> MagicLinkSent:
    """Always 202 for a human, whether or not the address has an account."""
    if not turnstile.verify(body.turnstile_token, _client_ip(request)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turnstile check failed")
    service.request_magic_link(body.email, body.next)
    return MagicLinkSent()


@router.post(
    "/magic-link/verify",
    responses={status.HTTP_400_BAD_REQUEST: {"description": "Expired or used link"}},
)
def verify_magic_link(body: MagicLinkVerify, request: Request, response: Response) -> SignInResult:
    signed_in = service.verify_magic_link(body.token, request.headers.get("user-agent"))
    if signed_in is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This sign-in link has expired or was already used"
        )
    set_session_cookie(response, signed_in.session_token)
    return SignInResult(next=signed_in.next_path)


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(response: Response, cp_session: Annotated[str | None, Cookie()] = None) -> None:
    if cp_session:
        service.end_session(cp_session)
    clear_session_cookie(response)


def _google(google: Annotated[GoogleSignIn | None, Depends(get_google)]) -> GoogleSignIn:
    if google is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not configured")
    return google


def _redirect_uri() -> str:
    return f"{get_settings().web_origin}/v1/auth/google/callback"


@router.get("/google/start", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND)
def google_start(
    google: Annotated[GoogleSignIn, Depends(_google)], next: str | None = None
) -> RedirectResponse:
    state, nonce, verifier = (secrets.token_urlsafe(24) for _ in range(3))
    response = RedirectResponse(
        google.authorization_url(
            state=state, nonce=nonce, code_verifier=verifier, redirect_uri=_redirect_uri()
        ),
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(
        OAUTH_COOKIE,
        sign(
            {"state": state, "nonce": nonce, "verifier": verifier, "next": safe_next(next)},
            get_settings().secret_key,
        ),
        max_age=OAUTH_MAX_AGE_SECONDS,
        httponly=True,
        secure=get_settings().web_origin.startswith("https://"),
        samesite="lax",
        path=OAUTH_COOKIE_PATH,
    )
    return response


@router.get(
    "/google/callback", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER
)
def google_callback(
    request: Request,
    google: Annotated[GoogleSignIn, Depends(_google)],
    code: str | None = None,
    state: str | None = None,
    cp_oauth: Annotated[str | None, Cookie()] = None,
) -> RedirectResponse:
    saved = (
        unsign(cp_oauth, get_settings().secret_key, max_age_seconds=OAUTH_MAX_AGE_SECONDS)
        if cp_oauth
        else None
    )
    identity = None
    if saved and code and state and secrets.compare_digest(state, saved["state"]):
        identity = google.identify(
            code=code,
            code_verifier=saved["verifier"],
            nonce=saved["nonce"],
            redirect_uri=_redirect_uri(),
        )
    if identity is None or saved is None:
        response = RedirectResponse("/signin?error=google", status_code=status.HTTP_303_SEE_OTHER)
    else:
        signed_in = service.sign_in_verified_email(
            identity.email, identity.name, saved["next"], request.headers.get("user-agent")
        )
        response = RedirectResponse(signed_in.next_path, status_code=status.HTTP_303_SEE_OTHER)
        set_session_cookie(response, signed_in.session_token)
    response.delete_cookie(OAUTH_COOKIE, path=OAUTH_COOKIE_PATH)
    return response


__all__ = ["SESSION_COOKIE", "router"]
