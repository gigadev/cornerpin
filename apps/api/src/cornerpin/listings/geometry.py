"""Lot shapes as GeoJSON in the API and PostGIS in the database (ADR-026).

Shapes arrive as GeoJSON Polygon or MultiPolygon in longitude/latitude (WGS 84) and are stored
as MultiPolygon, SRID 4326. PostGIS decides validity; the API adds two sanity checks that catch
common mistakes: coordinates that are not longitude/latitude (projected survey coordinates),
and shapes far from the subdivision (latitude and longitude swapped)."""

import json
import math
import re
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, JsonValue, model_validator
from sqlalchemy import Function, func, literal_column, select, text
from sqlalchemy.orm import Session

MAX_VERTICES = 5000
# Farther than this from the subdivision's location is almost certainly a mistake.
MAX_DISTANCE_M = 25_000

Position = Annotated[list[float], Field(min_length=2, max_length=3)]
Ring = Annotated[list[Position], Field(min_length=4)]


def _positions(rings: list[list[list[float]]]) -> list[list[float]]:
    return [position for ring in rings for position in ring]


def _check_positions(positions: list[list[float]]) -> None:
    if len(positions) > MAX_VERTICES:
        raise ValueError(f"Too many points (more than {MAX_VERTICES})")
    for position in positions:
        lng, lat = position[0], position[1]
        if not (math.isfinite(lng) and math.isfinite(lat)):
            raise ValueError("Coordinates must be numbers")
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise ValueError(
                "Coordinates must be longitude/latitude (WGS 84); these look like a projected"
                " coordinate system"
            )


class PolygonGeometry(BaseModel):
    type: Literal["Polygon"]
    coordinates: Annotated[list[Ring], Field(min_length=1)]

    @model_validator(mode="after")
    def _lng_lat(self) -> Self:
        _check_positions(_positions(self.coordinates))
        return self


class MultiPolygonGeometry(BaseModel):
    type: Literal["MultiPolygon"]
    coordinates: Annotated[list[Annotated[list[Ring], Field(min_length=1)]], Field(min_length=1)]

    @model_validator(mode="after")
    def _lng_lat(self) -> Self:
        _check_positions([p for polygon in self.coordinates for p in _positions(polygon)])
        return self


Shape = Annotated[PolygonGeometry | MultiPolygonGeometry, Field(discriminator="type")]


def to_postgis(shape: PolygonGeometry | MultiPolygonGeometry) -> Function[Any]:
    """A PostGIS MultiPolygon (2D, SRID 4326) from a validated shape."""
    return func.ST_Multi(
        func.ST_Force2D(func.ST_SetSRID(func.ST_GeomFromGeoJSON(shape.model_dump_json()), 4326))
    )


def from_postgis(geojson: str | None) -> MultiPolygonGeometry | None:
    """A shape from ST_AsGeoJSON output."""
    return None if geojson is None else MultiPolygonGeometry.model_validate(json.loads(geojson))


def as_geojson(column: Any) -> Function[str | None]:
    return func.ST_AsGeoJSON(column, 7)


def check_shape(
    session: Session, shape: PolygonGeometry | MultiPolygonGeometry, subdivision_id: UUID
) -> None:
    """422 unless PostGIS calls the shape valid and it is near the subdivision."""
    from cornerpin.listings.models import Subdivision

    geometry = to_postgis(shape)
    row = session.execute(
        select(
            func.ST_IsValid(geometry).label("valid"),
            func.ST_IsValidReason(geometry).label("reason"),
            func.ST_Distance(func.Geography(geometry), func.Geography(Subdivision.location)).label(
                "distance"
            ),
        ).where(Subdivision.id == subdivision_id)
    ).one()
    if not row.valid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"That shape isn't valid: {row.reason}"
        )
    if row.distance > MAX_DISTANCE_M:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"That shape is {row.distance / 1000:.0f} km from the subdivision. Are latitude and"
            " longitude swapped?",
        )


def overlapping_lots(session: Session, lot_id: UUID | None, subdivision_id: UUID) -> list[str]:
    """Numbers of other lots in the subdivision whose interiors overlap this lot's boundary.
    Shared edges are fine; overlapping interiors are reported, not refused."""
    rows = session.execute(
        text(
            "SELECT other.number FROM lots me JOIN lots other"
            " ON other.subdivision_id = me.subdivision_id AND other.id <> me.id"
            " WHERE me.id = :lot AND me.subdivision_id = :subdivision"
            " AND other.boundary IS NOT NULL AND me.boundary IS NOT NULL"
            " AND ST_Relate(me.boundary, other.boundary, '2********')"
            " ORDER BY other.number"
        ),
        {"lot": lot_id, "subdivision": subdivision_id},
    ).scalars()
    return list(rows)


# --- GeoJSON import ------------------------------------------------------------------------

NUMBER_KEYS = ("number", "lot", "lot_number", "lot_no", "lotnum", "lot_num", "name", "id")
LOT_PREFIX = re.compile(r"^\s*lot\s*(no\.?|number)?\s*#?\s*", re.IGNORECASE)
LOT_NUMBER = re.compile(r"^[A-Za-z0-9-]{1,16}$")


class Feature(BaseModel):
    type: Literal["Feature"]
    properties: dict[str, JsonValue] | None = None
    geometry: dict[str, JsonValue] | None = None


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"]
    features: Annotated[list[Feature], Field(max_length=2000)]
    crs: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def _wgs84(self) -> Self:
        # GeoJSON is WGS 84 by definition; an old-style "crs" naming anything else is a
        # projected export that would land in the wrong place.
        name = json.dumps(self.crs or {}).upper()
        if self.crs and not any(code in name for code in ("CRS84", "4326")):
            raise ValueError("Export the GeoJSON in WGS 84 (EPSG:4326) longitude/latitude")
        return self


def lot_number_of(properties: dict[str, JsonValue] | None) -> str | None:
    """The lot number in a feature's properties: the first of NUMBER_KEYS present (any case),
    with a leading "Lot" or "#" removed. None when there isn't a usable one."""
    if not properties:
        return None
    by_key = {key.lower(): value for key, value in properties.items()}
    for key in NUMBER_KEYS:
        value = by_key.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, int | str):
            number = LOT_PREFIX.sub("", str(value)).strip()
            if LOT_NUMBER.fullmatch(number):
                return number
    return None


def area_acres(session: Session, shape: PolygonGeometry | MultiPolygonGeometry) -> float:
    acres = session.scalar(
        select(func.ST_Area(func.Geography(to_postgis(shape))) / literal_column("4046.8564224"))
    )
    return round(float(acres or 0), 3)
