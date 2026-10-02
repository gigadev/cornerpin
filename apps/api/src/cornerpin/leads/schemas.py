"""Request and response shapes for buyer activity (P1-08): saved lots, inquiries, hold requests
and contact consent."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from cornerpin.core.fields import EmailAddress, Phone
from cornerpin.listings.models import LotStatus

Channel = Literal["email", "sms", "voice"]
HoldStatus = Literal["pending", "approved", "declined", "withdrawn"]

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Message = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class ContactChoices(BaseModel):
    """Whether the lot's owner may contact the buyer on each channel (ADR-022). Calls (voice)
    are not offered until Phase 4."""

    email: bool = False
    sms: bool = False


class BuyerLotState(BaseModel):
    """What the lot page needs to show a signed-in buyer's own activity on one lot."""

    saved: bool
    pending_hold: bool
    contact: ContactChoices
    email: str
    display_name: str | None
    phone: str | None


class SavedLot(BaseModel):
    lot_id: UUID
    number: str
    status: LotStatus
    price: int | None
    subdivision_name: str
    subdivision_slug: str
    saved_at: datetime


class InquiryCreate(BaseModel):
    name: PersonName
    email: EmailAddress | None = Field(
        default=None, description="Required when signed out; signed in, the account's is used."
    )
    phone: Phone | None = None
    message: Annotated[Message, StringConstraints(min_length=1)]
    turnstile_token: str | None = Field(default=None, description="Required when signed out.")
    contact: ContactChoices | None = Field(
        default=None, description="Signed in only. Omit to leave contact consent unchanged."
    )


class HoldRequestCreate(BaseModel):
    name: PersonName
    phone: Phone | None = None
    message: Message = ""
    contact: ContactChoices | None = Field(
        default=None, description="Omit to leave contact consent unchanged."
    )


class Created(BaseModel):
    id: UUID


class ConsentOut(BaseModel):
    """The current consent for one tenant and channel: its latest row."""

    tenant_id: UUID
    tenant_name: str
    channel: Channel
    granted: bool
    source: str
    recorded_at: datetime


class ConsentChange(BaseModel):
    tenant_id: UUID
    channel: Channel
    granted: bool


class InquiryOut(BaseModel):
    id: UUID
    lot_id: UUID
    lot_number: str
    subdivision_name: str
    name: str
    email: str
    phone: str | None
    message: str
    signed_in: bool
    contact: list[Channel] = Field(description="Channels the buyer currently allows")
    created_at: datetime


class HoldRequestOut(BaseModel):
    id: UUID
    lot_id: UUID
    lot_number: str
    lot_status: LotStatus
    subdivision_name: str
    name: str
    email: str
    phone: str | None
    message: str
    status: HoldStatus
    contact: list[Channel] = Field(description="Channels the buyer currently allows")
    created_at: datetime
    decided_at: datetime | None


class HoldDecision(BaseModel):
    decision: Literal["approve", "decline"]
