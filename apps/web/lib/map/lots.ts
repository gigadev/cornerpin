import type { Feature, FeatureCollection, MultiPolygon, Polygon, Position } from "geojson";
import type { LotStatus } from "@/lib/format";

// Base map: OpenFreeMap vector tiles, no key (ADR-018). Satellite comes from MapTiler and
// stays off until a key exists.
export const STREET_STYLE = "https://tiles.openfreemap.org/styles/liberty";
export function satelliteStyle(key: string): string {
  return `https://api.maptiler.com/maps/hybrid/style.json?key=${encodeURIComponent(key)}`;
}

/** Colours mean status, not brand: they stay when a brand arrives. */
export const STATUS_COLORS: Record<LotStatus, string> = {
  available: "#16a34a",
  on_hold: "#d97706",
  sold: "#71717a",
};

/** GraphQL enum values (AVAILABLE) as the portal's statuses (available). */
export function lotStatusFromGraphql(value: "AVAILABLE" | "ON_HOLD" | "SOLD"): LotStatus {
  return value.toLowerCase() as LotStatus;
}

export type MapLotInput = {
  id: string;
  number: string;
  status: LotStatus;
  boundary: MultiPolygon | null;
};

export type LotProperties = { id: string; number: string; status: LotStatus; color: string };

/** Lots with a shape, as map features. Lots without one are left off the map. */
export function lotFeatures(
  lots: readonly MapLotInput[],
): FeatureCollection<MultiPolygon, LotProperties> {
  const features: Feature<MultiPolygon, LotProperties>[] = [];
  for (const lot of lots) {
    if (!lot.boundary) continue;
    features.push({
      type: "Feature",
      id: lot.id,
      geometry: lot.boundary,
      properties: {
        id: lot.id,
        number: lot.number,
        status: lot.status,
        color: STATUS_COLORS[lot.status],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

export type Bounds = [west: number, south: number, east: number, north: number];

/** The box around every shape, or null when there are none. */
export function boundsOf(collection: FeatureCollection<MultiPolygon | Polygon>): Bounds | null {
  let bounds: Bounds | null = null;
  const visit = (position: Position) => {
    const [lng, lat] = position;
    if (lng === undefined || lat === undefined) return;
    bounds = bounds
      ? [
          Math.min(bounds[0], lng),
          Math.min(bounds[1], lat),
          Math.max(bounds[2], lng),
          Math.max(bounds[3], lat),
        ]
      : [lng, lat, lng, lat];
  };
  for (const feature of collection.features) {
    const polygons =
      feature.geometry.type === "Polygon"
        ? [feature.geometry.coordinates]
        : feature.geometry.coordinates;
    polygons.forEach((polygon) => polygon.forEach((ring) => ring.forEach(visit)));
  }
  return bounds;
}

/** The first polygon of a lot's shape, for the editor, which edits one polygon at a time. */
export function firstPolygon(boundary: MultiPolygon): Polygon | null {
  const coordinates = boundary.coordinates[0];
  return coordinates ? { type: "Polygon", coordinates } : null;
}
