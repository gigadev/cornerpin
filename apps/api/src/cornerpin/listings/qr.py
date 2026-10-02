"""QR codes for lot signs (P1-11, ADR-031). A code names a lot, not a URL: /q/{code} looks the
lot up when it's scanned, so a sign keeps working when the subdivision's slug changes."""

import secrets
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from cornerpin.core.auth.deps import SignedInUser
from cornerpin.core.tenancy import tenant_session
from cornerpin.listings.models import Lot

# Lowercase letters and digits without the look-alikes (0/o, 1/l/i), in case someone types one
# from a sign. Must match the CHECK on qr_codes.code: ^[a-z0-9]{6,16}$.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LENGTH = 8
CODE_PATTERN = r"^[a-z0-9]{6,16}$"

router = APIRouter(prefix="/tenants/{tenant_id}", tags=["listings"])

Responses = dict[int | str, dict[str, Any]]
NOT_FOUND: Responses = {status.HTTP_404_NOT_FOUND: {"description": "Not found, or not your tenant"}}


class QrCode(BaseModel):
    code: str = Field(description="Signs link to /q/{code}")


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def _existing(session: Session, lot_id: UUID) -> str | None:
    code: str | None = session.execute(
        text("SELECT code FROM qr_codes WHERE lot_id = :l"), {"l": lot_id}
    ).scalar_one_or_none()
    return code


@router.post("/lots/{lot_id}/qr-code", responses=NOT_FOUND)
def lot_qr_code(tenant_id: UUID, lot_id: UUID, user: SignedInUser) -> QrCode:
    """The lot's code, created the first time it's asked for. Always the same afterwards."""
    with tenant_session(user, tenant_id) as session:
        if session.get(Lot, lot_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        for _ in range(5):
            code = _existing(session, lot_id)
            if code:
                return QrCode(code=code)
            # Conflicts on either the lot (someone else just made its code) or the code itself
            # (a collision) insert nothing; the loop then reads or retries.
            session.execute(
                text(
                    "INSERT INTO qr_codes (code, tenant_id, lot_id) VALUES (:c, :t, :l)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"c": new_code(), "t": tenant_id, "l": lot_id},
            )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not make a code; try again")
