import type { FeatureCollection, MultiPolygon } from "geojson";
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { boundsOf, type LotProperties } from "@/lib/map/lots";

// The lot layers both maps draw: fill by status colour, outline, and the lot number.

export const LOTS_SOURCE = "lots";
export const LOTS_FILL = "lots-fill";
export const LOTS_OUTLINE = "lots-outline";
export const LOTS_LABEL = "lots-label";

export type LotCollection = FeatureCollection<MultiPolygon, LotProperties>;

/** Add (or, after a style change, re-add) the lot source and layers. */
export function addLotLayers(map: MapLibreMap, lots: LotCollection): void {
  if (map.getSource(LOTS_SOURCE)) return;
  map.addSource(LOTS_SOURCE, { type: "geojson", data: lots, promoteId: "id" });
  map.addLayer({
    id: LOTS_FILL,
    type: "fill",
    source: LOTS_SOURCE,
    paint: { "fill-color": ["get", "color"], "fill-opacity": 0.4 },
  });
  map.addLayer({
    id: LOTS_OUTLINE,
    type: "line",
    source: LOTS_SOURCE,
    paint: { "line-color": ["get", "color"], "line-width": 2 },
  });
  map.addLayer({
    id: LOTS_LABEL,
    type: "symbol",
    source: LOTS_SOURCE,
    layout: {
      "text-field": ["get", "number"],
      // A font the base map's glyph server has; MapLibre's default (Open Sans) isn't there.
      "text-font": ["Noto Sans Regular"],
      "text-size": 12,
      "text-allow-overlap": false,
    },
    paint: { "text-color": "#1c1917", "text-halo-color": "#ffffff", "text-halo-width": 1.5 },
  });
}

export function setLots(map: MapLibreMap, lots: LotCollection): void {
  map.getSource<GeoJSONSource>(LOTS_SOURCE)?.setData(lots);
}

type Filter = Parameters<MapLibreMap["setFilter"]>[1];

/** Hide one lot from the static layers, e.g. while its shape is being edited. */
export function hideLot(map: MapLibreMap, lotId: string | null): void {
  const filter: Filter = lotId ? ["!=", ["get", "id"], lotId] : null;
  for (const layer of [LOTS_FILL, LOTS_OUTLINE, LOTS_LABEL]) {
    if (map.getLayer(layer)) map.setFilter(layer, filter);
  }
}

export function fitToLots(
  map: MapLibreMap,
  lots: LotCollection,
  { animate = false, maxZoom = 18 }: { animate?: boolean; maxZoom?: number } = {},
): void {
  const bounds = boundsOf(lots);
  if (!bounds) return;
  map.fitBounds(
    [
      [bounds[0], bounds[1]],
      [bounds[2], bounds[3]],
    ],
    { padding: 40, maxZoom, animate },
  );
}

/** Numbers of the lots currently drawn on screen, sorted; exposed for smoke tests. */
export function renderedLotNumbers(map: MapLibreMap): string {
  if (!map.getLayer(LOTS_FILL)) return "";
  const numbers = new Set<string>();
  for (const feature of map.queryRenderedFeatures({ layers: [LOTS_FILL] })) {
    const number: unknown = feature.properties["number"];
    if (typeof number === "string") numbers.add(number);
  }
  return [...numbers].sort((a, b) => a.localeCompare(b, "en", { numeric: true })).join(",");
}
