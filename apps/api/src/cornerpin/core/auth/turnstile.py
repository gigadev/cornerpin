"""Cloudflare Turnstile (ADR-008). Verification is part of handling the form, so it runs in the
request; it is a bot check on our own endpoint, not a side effect (ADR-023)."""

from functools import lru_cache
from typing import Protocol

import httpx
from fastapi import Request

from cornerpin.core.config import get_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileVerifier(Protocol):
    def verify(self, token: str, remote_ip: str | None) -> bool: ...


class CloudflareTurnstile:
    def __init__(self, secret_key: str) -> None:
        self._secret_key = secret_key

    def verify(self, token: str, remote_ip: str | None) -> bool:
        if not token:
            return False
        data = {"secret": self._secret_key, "response": token}
        if remote_ip:
            data["remoteip"] = remote_ip
        try:
            response = httpx.post(VERIFY_URL, data=data, timeout=10)
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return response.json().get("success") is True


@lru_cache
def get_turnstile() -> TurnstileVerifier:
    return CloudflareTurnstile(get_settings().turnstile_secret_key)


def client_ip(request: Request) -> str | None:
    """The visitor's address, for Turnstile. Behind Cloud Run the first forwarded hop."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
