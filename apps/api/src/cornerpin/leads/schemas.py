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


# --- leads (P2-02, ADR-035) -----------------------------------------------------------------

LeadStage = Literal["new", "contacted", "engaged", "holding", "won", "lost"]
LeadEventKind = Literal[
    "inquiry",
    "hold_requested",
    "hold_approved",
    "hold_declined",
    "hold_withdrawn",
    "consent_changed",
    "stage_changed",
    "note",
    "handoff",
    "handoff_resolved",
]
NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class LeadLot(BaseModel):
    lot_id: UUID
    number: str
    subdivision_name: str


class LeadSummary(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    stage: LeadStage
    source: str = Field(description="What first brought the buyer: inquiry, hold_request, ...")
    signed_in: bool = Field(description="Whether the buyer has signed in, so their email is proven")
    contact: list[Channel] = Field(description="Channels the buyer currently allows")
    lots: list[LeadLot] = Field(description="Lots the buyer has asked about or held")
    handoff_at: datetime | None = Field(description="Set while the lead needs a person")
    handoff_reason: str | None
    last_activity_at: datetime
    created_at: datetime


class StageCount(BaseModel):
    stage: LeadStage
    count: int


class LeadList(BaseModel):
    leads: list[LeadSummary]
    stages: list[StageCount] = Field(description="Every stage, with how many leads are in it")
    needs_human: int = Field(description="Leads waiting for a person")


class LeadEvent(BaseModel):
    """One timeline entry. Which optional fields are set depends on `kind`."""

    id: UUID
    kind: LeadEventKind
    created_at: datetime
    by_buyer: bool = Field(description="The buyer's own action (an inquiry, hold or consent)")
    verified: bool = Field(description="False for an anonymous inquiry, whose email is unproven")
    actor_email: str | None = Field(description="Who acted, if a person signed in did")
    lot: LeadLot | None
    message: str | None
    note: str | None
    channel: Channel | None
    granted: bool | None
    consent_source: str | None
    from_stage: LeadStage | None
    to_stage: LeadStage | None
    reason: str | None


class LeadDetail(LeadSummary):
    events: list[LeadEvent] = Field(description="Newest first")


class LeadUpdate(BaseModel):
    stage: LeadStage


class NoteCreate(BaseModel):
    text: NoteText
