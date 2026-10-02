"""Public, read-only GraphQL for browsing listings (ADR-007). Every resolver runs in a
public_session, so row-level security alone decides what is visible: published subdivisions and
their published lots, nothing else. No mutations.

Photos and documents are resolved per lot only when asked for, so the subdivision page does not
load every lot's media. Their files are served by the REST routes in public_files.py."""

import re
from typing import Any, NewType
from uuid import UUID

import strawberry
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from strawberry.extensions import MaxTokensLimiter, QueryDepthLimiter
from strawberry.fastapi import GraphQLRouter

from cornerpin.core.config import get_settings
from cornerpin.core.db import public_session
from cornerpin.listings.geometry import as_geojson, from_postgis
from cornerpin.listings.models import (
    DocumentKind,
    ListingType,
    Lot,
    LotDocument,
    LotPhoto,
    LotStatus,
    Phase,
    Subdivision,
    lot_number_order,
)
from cornerpin.listings.qr import CODE_PATTERN

# A GeoJSON geometry, passed through as JSON; typed in TypeScript by GraphQL codegen.
GeoJSONValue = NewType("GeoJSONValue", dict[str, object])
GEOJSON_SCALAR = strawberry.scalar(
    name="GeoJSON",
    description="A GeoJSON geometry in longitude/latitude (WGS 84); lots are MultiPolygons.",
)

PublicLotStatus = strawberry.enum(LotStatus, name="LotStatus")
PublicListingType = strawberry.enum(ListingType, name="ListingType")
PublicDocumentKind = strawberry.enum(DocumentKind, name="DocumentKind")


@strawberry.type(description="A photo of a published lot, in its display order.")
class PublicPhoto:
    id: strawberry.ID
    url: str = strawberry.field(description="Same-origin path to the image")
    caption: str
    width: int | None
    height: int | None


@strawberry.type(description="A document attached to a published lot.")
class PublicDocument:
    id: strawberry.ID
    kind: PublicDocumentKind  # pyright: ignore[reportInvalidTypeForm]
    title: str
    size_bytes: int
    url: str = strawberry.field(description="Same-origin path; downloads under the title")


@strawberry.type(description="The house on a lot + home listing.")
class PublicHome:
    bedrooms: int | None
    bathrooms: float | None
    square_feet: int | None
    description: str | None


@strawberry.type(description="A published lot.")
class PublicLot:
    lot_id: strawberry.Private[UUID]
    id: strawberry.ID
    number: str
    status: PublicLotStatus  # pyright: ignore[reportInvalidTypeForm]
    listing_type: PublicListingType  # pyright: ignore[reportInvalidTypeForm]
    price: int | None = strawberry.field(description="Whole dollars; null when not priced yet.")
    acreage: float | None
    phase_name: str
    boundary: GeoJSONValue | None
    location: list[float] = strawberry.field(
        description="[longitude, latitude] for directions: inside the lot's shape, or the"
        " subdivision's location when the lot has no shape yet."
    )
    home: PublicHome | None

    @strawberry.field(description="Photos in the owner's order.")
    def photos(self) -> list[PublicPhoto]:
        with public_session() as session:
            photos = session.scalars(
                select(LotPhoto)
                .where(LotPhoto.lot_id == self.lot_id)
                .order_by(LotPhoto.sort_order, LotPhoto.created_at)
            ).all()
            return [
                PublicPhoto(
                    id=strawberry.ID(str(photo.id)),
                    url=f"/v1/public/photos/{photo.id}/file",
                    caption=photo.caption,
                    width=photo.width,
                    height=photo.height,
                )
                for photo in photos
            ]

    @strawberry.field(description="Plat, survey, covenants, utilities and other documents.")
    def documents(self) -> list[PublicDocument]:
        with public_session() as session:
            documents = session.scalars(
                select(LotDocument)
                .where(LotDocument.lot_id == self.lot_id)
                .order_by(LotDocument.kind, LotDocument.title)
            ).all()
            return [
                PublicDocument(
                    id=strawberry.ID(str(document.id)),
                    kind=document.kind,
                    title=document.title,
                    size_bytes=document.size_bytes,
                    url=f"/v1/public/documents/{document.id}/file",
                )
                for document in documents
            ]


@strawberry.type(description="A published subdivision.")
class PublicSubdivision:
    slug: str
    name: str
    description: str
    time_zone: str
    center: list[float] = strawberry.field(description="[longitude, latitude]")
    lots: list[PublicLot]


def _geojson(text: str | None) -> GeoJSONValue | None:
    shape = from_postgis(text)
    return None if shape is None else GeoJSONValue(shape.model_dump())


def _lot_rows(session: Session, subdivision: Subdivision, *conditions: Any) -> list[PublicLot]:
    inside = func.ST_PointOnSurface(Lot.boundary)
    rows = session.execute(
        select(
            Lot,
            Phase.name,
            as_geojson(Lot.boundary),
            func.ST_X(inside),
            func.ST_Y(inside),
        )
        .join(Phase, Phase.id == Lot.phase_id)
        .where(Lot.subdivision_id == subdivision.id, *conditions)
        .order_by(*lot_number_order())
    ).all()
    lots: list[PublicLot] = []
    for lot, phase_name, geojson, lng, lat in rows:
        has_home = lot.listing_type == ListingType.LOT_AND_HOME
        lots.append(
            PublicLot(
                lot_id=lot.id,
                id=strawberry.ID(str(lot.id)),
                number=lot.number,
                status=lot.status,
                listing_type=lot.listing_type,
                price=int(lot.price) if lot.price is not None else None,
                acreage=float(lot.acreage) if lot.acreage is not None else None,
                phase_name=phase_name,
                boundary=_geojson(geojson),
                location=[lng, lat]
                if lng is not None and lat is not None
                else [subdivision.longitude, subdivision.latitude],
                home=PublicHome(
                    bedrooms=lot.home_bedrooms,
                    bathrooms=float(lot.home_bathrooms) if lot.home_bathrooms is not None else None,
                    square_feet=lot.home_square_feet,
                    description=lot.home_description,
                )
                if has_home
                else None,
            )
        )
    return lots


@strawberry.type(description="Where a sign's QR code points right now.")
class QrTarget:
    subdivision_slug: str
    lot_number: str


def _subdivision(session: Session, slug: str) -> Subdivision | None:
    return session.scalar(select(Subdivision).where(Subdivision.slug == slug))


@strawberry.type
class Query:
    @strawberry.field(description="A published subdivision by its web address, or null.")
    def subdivision(self, slug: str) -> PublicSubdivision | None:
        with public_session() as session:
            found = _subdivision(session, slug)
            if found is None:
                return None
            return PublicSubdivision(
                slug=found.slug,
                name=found.name,
                description=found.description,
                time_zone=found.time_zone,
                center=[found.longitude, found.latitude],
                lots=_lot_rows(session, found),
            )

    @strawberry.field(description="A published lot by subdivision web address and lot number.")
    def lot(self, subdivision_slug: str, number: str) -> PublicLot | None:
        with public_session() as session:
            found = _subdivision(session, subdivision_slug)
            if found is None:
                return None
            lots = _lot_rows(session, found, Lot.number == number)
            return lots[0] if lots else None

    @strawberry.field(
        description="The published lot a sign's QR code names, or null (ADR-031). Looked up "
        "when scanned, so a renamed subdivision still works."
    )
    def qr_target(self, code: str) -> QrTarget | None:
        if not re.fullmatch(CODE_PATTERN, code):
            return None
        with public_session() as session:
            row = session.execute(
                text(
                    "SELECT s.slug, l.number FROM qr_codes q JOIN lots l ON l.id = q.lot_id"
                    " JOIN subdivisions s ON s.id = l.subdivision_id WHERE q.code = :code"
                ),
                {"code": code},
            ).one_or_none()
        return None if row is None else QrTarget(subdivision_slug=row.slug, lot_number=row.number)


schema = strawberry.Schema(
    query=Query,
    scalar_overrides={GeoJSONValue: GEOJSON_SCALAR},
    extensions=[
        lambda: QueryDepthLimiter(max_depth=6),
        lambda: MaxTokensLimiter(max_token_count=2000),
    ],
)


def graphql_router() -> GraphQLRouter[None, None]:
    return GraphQLRouter(
        schema,
        graphql_ide="graphiql" if get_settings().is_local else None,
        allow_queries_via_get=True,
    )
