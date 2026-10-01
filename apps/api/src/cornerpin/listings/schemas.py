"""Request and response shapes for the owner portal. Prices are whole dollars; the database
keeps cents for the future but the portal never shows them."""

import re
from datetime import datetime
from functools import cache
from typing import Annotated, Self
from uuid import UUID
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, model_validator

from cornerpin.listings.models import ListingType, LotStatus, ReleaseStatus

# Must match the CHECK constraint on subdivisions.slug (migration 0002); tests/test_listings.py
# checks that the database rejects every one of these.
RESERVED_SLUGS = frozenset(
    {
        "app", "q", "api", "v1", "graphql", "internal", "serwist", "icons", "static", "admin",
        "auth", "login", "logout", "signin", "signup", "account", "settings", "about", "help",
        "terms", "privacy", "offline",
    }
)  # fmt: skip
SLUG_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def _slug(value: str) -> str:
    if not SLUG_PATTERN.fullmatch(value):
        raise ValueError(
            "Use lowercase letters, digits and hyphens, starting and ending with a letter or digit"
        )
    if value in RESERVED_SLUGS:
        raise ValueError("That web address is reserved")
    return value


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _time_zone(value: str) -> str:
    if value not in _time_zones():
        raise ValueError("Not a known time zone, e.g. America/Boise")
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Slug = Annotated[str, AfterValidator(_slug)]
TimeZone = Annotated[str, AfterValidator(_time_zone)]
Description = Annotated[str, StringConstraints(max_length=5000)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
LotNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9-]{1,16}$")
]
Dollars = Annotated[int, Field(ge=0, le=9_999_999_999)]
Acres = Annotated[float, Field(gt=0, lt=1_000_000)]


# --- subdivisions --------------------------------------------------------------------------


class SubdivisionCreate(BaseModel):
    name: Name
    slug: Slug
    time_zone: TimeZone
    latitude: Latitude
    longitude: Longitude
    description: Description = ""
    published: bool = False


class SubdivisionUpdate(BaseModel):
    """Only the fields sent are changed."""

    name: Name | None = None
    slug: Slug | None = None
    time_zone: TimeZone | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    description: Description | None = None
    published: bool | None = None

    @model_validator(mode="after")
    def _location_together(self) -> Self:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Send latitude and longitude together")
        return self


class SubdivisionSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    time_zone: str
    published: bool
    lot_count: int
    available_count: int


# --- phases --------------------------------------------------------------------------------


class PhaseCreate(BaseModel):
    name: Name
    sort_order: int = Field(default=0, ge=0, le=10_000)
    release_status: ReleaseStatus = ReleaseStatus.UPCOMING


class PhaseUpdate(BaseModel):
    name: Name | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10_000)
    release_status: ReleaseStatus | None = None


class PhaseOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    release_status: ReleaseStatus
    lot_count: int


# --- lots ----------------------------------------------------------------------------------


class Home(BaseModel):
    """The house on a lot + home listing. All optional while a home is being finished."""

    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: float | None = Field(default=None, ge=0, le=50, multiple_of=0.5)
    square_feet: int | None = Field(default=None, gt=0, le=100_000)
    description: str | None = Field(default=None, max_length=5000)


class LotCreate(BaseModel):
    number: LotNumber
    phase_id: UUID
    acreage: Acres | None = None
    price: Dollars | None = None
    status: LotStatus = LotStatus.AVAILABLE
    listing_type: ListingType = ListingType.LAND_ONLY
    home: Home | None = None
    published: bool = False

    @model_validator(mode="after")
    def _home_only_with_lot_and_home(self) -> Self:
        if self.listing_type == ListingType.LAND_ONLY and self.home is not None:
            raise ValueError("A land-only lot has no home details")
        return self


class LotUpdate(BaseModel):
    """Only the fields sent are changed; send null to clear acreage, price or home."""

    number: LotNumber | None = None
    phase_id: UUID | None = None
    acreage: Acres | None = None
    price: Dollars | None = None
    status: LotStatus | None = None
    listing_type: ListingType | None = None
    home: Home | None = None
    published: bool | None = None

    @model_validator(mode="after")
    def _home_only_with_lot_and_home(self) -> Self:
        if self.listing_type == ListingType.LAND_ONLY and self.home is not None:
            raise ValueError("A land-only lot has no home details")
        return self


class LotSummary(BaseModel):
    id: UUID
    number: str
    phase_id: UUID
    phase_name: str
    status: LotStatus
    listing_type: ListingType
    price: int | None
    acreage: float | None
    published: bool


class StatusChange(BaseModel):
    from_status: LotStatus | None
    to_status: LotStatus
    changed_by_email: str | None
    changed_at: datetime


class PriceChange(BaseModel):
    from_price: int | None
    to_price: int | None
    changed_by_email: str | None
    changed_at: datetime


class LotDetail(BaseModel):
    id: UUID
    subdivision_id: UUID
    subdivision_name: str
    time_zone: str  # the subdivision's; history times are shown in it
    phase_id: UUID
    number: str
    acreage: float | None
    price: int | None
    status: LotStatus
    listing_type: ListingType
    home: Home | None
    published: bool
    updated_at: datetime
    status_history: list[StatusChange]
    price_history: list[PriceChange]


class SubdivisionDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    time_zone: str
    latitude: float
    longitude: float
    description: str
    published: bool
    phases: list[PhaseOut]
    lots: list[LotSummary]
