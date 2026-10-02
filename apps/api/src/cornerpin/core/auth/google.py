"""Google sign-in (OpenID Connect, authorization code with PKCE). Dormant until
GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET exist (ADR-008)."""

import base64
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt

from cornerpin.core.config import get_settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 -- a URL, not a password
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    name: str | None


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class GoogleSignIn(Protocol):
    def authorization_url(
        self, *, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str: ...

    def identify(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> GoogleIdentity | None: ...


class GoogleOidc:
    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._jwks = jwt.PyJWKClient(JWKS_URL)

    def authorization_url(
        self, *, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str:
        query = urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": pkce_challenge(code_verifier),
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def identify(
        self, *, code: str, code_verifier: str, nonce: str, redirect_uri: str
    ) -> GoogleIdentity | None:
        """Exchange the code and verify the ID token. None unless Google vouches for a verified
        email address."""
        response = httpx.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=10,
        )
        if response.status_code != 200:
            return None
        id_token = str(response.json().get("id_token", ""))
        try:
            key = self._jwks.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                key.key,
                algorithms=["RS256"],
                audience=self._client_id,
                issuer=ISSUERS,
            )
        except jwt.PyJWTError:
            return None
        if claims.get("nonce") != nonce or claims.get("email_verified") is not True:
            return None
        email = claims.get("email")
        if not isinstance(email, str):
            return None
        name = claims.get("name")
        return GoogleIdentity(email=email, name=name if isinstance(name, str) else None)


@lru_cache
def get_google() -> GoogleSignIn | None:
    settings = get_settings()
    if not (settings.google_client_id and settings.google_client_secret):
        return None
    return GoogleOidc(settings.google_client_id, settings.google_client_secret)
