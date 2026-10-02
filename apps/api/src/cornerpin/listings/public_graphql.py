"""Public, read-only GraphQL for browsing listings (ADR-007). Every resolver runs in a
public_session, so row-level security alone decides what is visible: published subdivisions and
their published lots, nothing else. No mutations.

P1-06 serves the map (shapes and statuses); P1-07 adds the rest of the public pages."""

from typing import NewType
from uuid import UUID

import strawberry
from sqlalchemy import select
from strawberry.extensions import MaxTokensLimiter, QueryDepthLimiter
from strawberry.fastapi import GraphQLRouter

from cornerpin.core.config import get_settings
from cornerpin.core.db import public_session
from cornerpin.listings.geometry import as_geojson, from_postgis
from cornerpin.listings.models import (
    ListingType,
    Lot,
    LotStatus,
    Subdivision,
    lot_number_order,
)

# A GeoJSON geometry, passed through as JSON; typed in TypeScript by GraphQL codegen.
GeoJSONValue = NewType("GeoJSONValue", dict[str, object])
GEOJSON_SCALAR = strawberry.scalar(
    name="GeoJSON",
    description="A GeoJSON geometry in longitude/latitude (WGS 84); lots are MultiPolygons.",
)

PublicLotStatus = strawberry.enum(LotStatus, name="LotStatus")
PublicListingType = strawberry.enum(ListingType, name="ListingType")


@strawberry.type(description="A published lot.")
class PublicLot:
    id: strawberry.ID
    number: str
    status: PublicLotStatus  # pyright: ignore[reportInvalidTypeForm]
    listing_type: PublicListingType  # pyright: ignore[reportInvalidTypeForm]
    price: int | None = strawberry.field(description="Whole dollars; null when not priced yet.")
    acreage: float | None
    boundary: GeoJSONValue | None


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


def _lots(subdivision_id: UUID) -> list[PublicLot]:
    with public_session() as session:
        rows = session.execute(
            select(Lot, as_geojson(Lot.boundary))
            .where(Lot.subdivision_id == subdivision_id)
            .order_by(*lot_number_order())
        ).all()
        return [
            PublicLot(
                id=strawberry.ID(str(lot.id)),
                number=lot.number,
                status=lot.status,
                listing_type=lot.listing_type,
                price=int(lot.price) if lot.price is not None else None,
                acreage=float(lot.acreage) if lot.acreage is not None else None,
                boundary=_geojson(geojson),
            )
            for lot, geojson in rows
        ]


@strawberry.type
class Query:
    @strawberry.field(description="A published subdivision by its web address, or null.")
    def subdivision(self, slug: str) -> PublicSubdivision | None:
        with public_session() as session:
            found = session.scalar(select(Subdivision).where(Subdivision.slug == slug))
            if found is None:
                return None
            subdivision_id = found.id
            result = PublicSubdivision(
                slug=found.slug,
                name=found.name,
                description=found.description,
                time_zone=found.time_zone,
                center=[found.longitude, found.latitude],
                lots=[],
            )
        result.lots = _lots(subdivision_id)
        return result


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
