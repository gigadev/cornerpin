"""Sealing integration credentials (ADR-040). AES-256-GCM with the app's integrations key; the
tenant and provider are bound in as associated data, so a sealed value copied to another tenant's
row, or another provider's, doesn't open."""

import base64
import json
import os
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cornerpin.core.config import get_settings

VERSION = b"\x01"  # the format, so the key can be rotated later
NONCE_BYTES = 12


class Unsealable(Exception):
    """The sealed value was altered, belongs elsewhere, or was sealed with another key."""


def _cipher() -> AESGCM:
    return AESGCM(base64.b64decode(get_settings().integrations_key))


def _context(tenant_id: UUID, provider: str) -> bytes:
    return f"{tenant_id}:{provider}".encode()


def seal(tenant_id: UUID, provider: str, secret: dict[str, Any]) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    sealed = _cipher().encrypt(nonce, json.dumps(secret).encode(), _context(tenant_id, provider))
    return VERSION + nonce + sealed


def unseal(tenant_id: UUID, provider: str, sealed: bytes) -> dict[str, Any]:
    if sealed[:1] != VERSION:
        raise Unsealable("unknown format")
    nonce, body = sealed[1 : 1 + NONCE_BYTES], sealed[1 + NONCE_BYTES :]
    try:
        plain = _cipher().decrypt(nonce, body, _context(tenant_id, provider))
    except InvalidTag as exc:
        raise Unsealable("altered, misplaced or another key") from exc
    value: dict[str, Any] = json.loads(plain)
    return value
