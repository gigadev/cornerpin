"""ORM models for the listings module. The migrations own the schema (tables, policies,
triggers); these map it for typed queries, and tests/test_models.py checks they agree."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import DateTime, ForeignKeyConstraint, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, column_property, mapped_column
from sqlalchemy.types import TypeEngine


class Base(DeclarativeBase):
    # Every timestamp in the schema is timestamptz.
    type_annotation_map: ClassVar[dict[type, TypeEngine[Any]]] = {datetime: DateTime(timezone=True)}


class LotStatus(StrEnum):
    AVAILABLE = "available"
    ON_HOLD = "on_hold"
    SOLD = "sold"


class ListingType(StrEnum):
    LAND_ONLY = "land_only"
    LOT_AND_HOME = "lot_and_home"


class ReleaseStatus(StrEnum):
    UPCOMING = "upcoming"
    RELEASED = "released"


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


def _enum(enum: type[StrEnum], name: str) -> ENUM:
    # Store the lowercase values the database enum uses, not the Python member names.
    return ENUM(enum, name=name, create_type=False, values_callable=_values)


class Subdivision(Base):
    __tablename__ = "subdivisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    location: Mapped[WKBElement] = mapped_column(Geometry("POINT", srid=4326, spatial_index=False))
    boundary: Mapped[WKBElement | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
    time_zone: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    published: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    latitude: Mapped[float] = column_property(func.ST_Y(location))
    longitude: Mapped[float] = column_property(func.ST_X(location))


class Phase(Base):
    __tablename__ = "phases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subdivision_id", "tenant_id"], ["subdivisions.id", "subdivisions.tenant_id"]
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    subdivision_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(server_default="0")
    release_status: Mapped[ReleaseStatus] = mapped_column(
        _enum(ReleaseStatus, "phase_release_status"), server_default="upcoming"
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Lot(Base):
    __tablename__ = "lots"
    __table_args__ = (
        ForeignKeyConstraint(
            ["subdivision_id", "tenant_id"], ["subdivisions.id", "subdivisions.tenant_id"]
        ),
        ForeignKeyConstraint(
            ["phase_id", "subdivision_id"], ["phases.id", "phases.subdivision_id"]
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    subdivision_id: Mapped[UUID]
    phase_id: Mapped[UUID]
    number: Mapped[str] = mapped_column(Text)
    boundary: Mapped[WKBElement | None] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
    )
    acreage: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[LotStatus] = mapped_column(
        _enum(LotStatus, "lot_status"), server_default="available"
    )
    listing_type: Mapped[ListingType] = mapped_column(
        _enum(ListingType, "listing_type"), server_default="land_only"
    )
    home_bedrooms: Mapped[int | None] = mapped_column(SmallInteger)
    home_bathrooms: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    home_square_feet: Mapped[int | None]
    home_description: Mapped[str | None] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LotStatusChange(Base):
    __tablename__ = "lot_status_history"
    __table_args__ = (ForeignKeyConstraint(["lot_id", "tenant_id"], ["lots.id", "lots.tenant_id"]),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    lot_id: Mapped[UUID]
    from_status: Mapped[LotStatus | None] = mapped_column(_enum(LotStatus, "lot_status"))
    to_status: Mapped[LotStatus] = mapped_column(_enum(LotStatus, "lot_status"))
    changed_by: Mapped[UUID | None]
    changed_by_email: Mapped[str | None] = mapped_column(CITEXT)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class LotPriceChange(Base):
    __tablename__ = "lot_price_history"
    __table_args__ = (ForeignKeyConstraint(["lot_id", "tenant_id"], ["lots.id", "lots.tenant_id"]),)

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID]
    lot_id: Mapped[UUID]
    from_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    to_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    changed_by: Mapped[UUID | None]
    changed_by_email: Mapped[str | None] = mapped_column(CITEXT)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
