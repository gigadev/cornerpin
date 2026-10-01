"""Opaque tokens and signed values. Raw tokens go to the user; only their SHA-256 is stored."""

import base64
import hashlib
import hmac
import json
import secrets
import time


def new_token() -> tuple[str, bytes]:
    """A random URL-safe token and the hash to store for it."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()


def safe_next(path: str | None) -> str:
    """Only same-site relative paths; anything else becomes '/'. Prevents open redirects."""
    if not path or not path.startswith("/") or path.startswith(("//", "/\\")):
        return "/"
    return path


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign(value: dict[str, str], secret: str) -> str:
    """Serialize and sign a small dict with a timestamp (HMAC-SHA256)."""
    body = _b64(json.dumps({"v": value, "t": int(time.time())}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def unsign(signed: str, secret: str, *, max_age_seconds: int) -> dict[str, str] | None:
    """The signed dict, or None if it was tampered with, malformed or is too old."""
    body, _, mac = signed.partition(".")
    expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    if not mac or not hmac.compare_digest(mac, expected):
        return None
    try:
        data = json.loads(_unb64(body))
        issued = int(data["t"])
        value = {str(k): str(v) for k, v in dict(data["v"]).items()}
    except (ValueError, KeyError, TypeError):
        return None
    if time.time() - issued > max_age_seconds:
        return None
    return value
