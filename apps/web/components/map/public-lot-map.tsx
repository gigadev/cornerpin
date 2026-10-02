"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import type { Map as MapLibreMap } from "maplibre-gl";
import { loadMapLibre } from "@/lib/map/load-maplibre";
import { useEffect, useMemo, useRef, useState } from "react";
import { STATUS_COLORS, STREET_STYLE, lotFeatures, satelliteStyle, type MapLotInput } from "@/lib/map/lots";
import { statusLabel, LOT_STATUSES } from "@/lib/format";
import { addLotLayers, fitToLots, renderedLotNumbers } from "./lot-layers";

/** The public subdivision map: published lots coloured by status (P1-06, P1-07). */
export function PublicLotMap({
  center,
  lots,
  satelliteKey,
}: {
  center: [number, number];
  lots: MapLotInput[];
  satelliteKey: string | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [rendered, setRendered] = useState("");
  const [satellite, setSatellite] = useState(false);
  const collection = useMemo(() => lotFeatures(lots), [lots]);
  const [lng, lat] = center;

  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    // Imported here: MapLibre needs a browser, and this keeps it out of the server render.
    void loadMapLibre().then(({ Map }) => {
      if (cancelled || !container.current) return;
      map = new Map({
        container: container.current,
        style: STREET_STYLE,
        center: [lng, lat],
        zoom: 15,
        attributionControl: { compact: true },
      });
      mapRef.current = map;
      const current = map;
      current.on("style.load", () => addLotLayers(current, collection));
      current.once("load", () => fitToLots(current, collection));
      current.on("idle", () => setRendered(renderedLotNumbers(current)));
    });
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
  }, [collection, lng, lat]);

  function toggleSatellite() {
    if (!satelliteKey || !mapRef.current) return;
    const next = !satellite;
    mapRef.current.setStyle(next ? satelliteStyle(satelliteKey) : STREET_STYLE);
    setSatellite(next);
  }

  return (
    <div className="grid gap-2">
      <div
        ref={container}
        role="region"
        aria-label="Map of lots"
        data-rendered-lots={rendered}
        className="h-[60vh] min-h-80 w-full overflow-hidden rounded-lg border border-border"
      />
      <div className="flex flex-wrap items-center gap-4 text-sm">
        {LOT_STATUSES.map((status) => (
          <span key={status} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-3 rounded-sm"
              style={{ backgroundColor: STATUS_COLORS[status] }}
            />
            {statusLabel(status)}
          </span>
        ))}
        {satelliteKey ? (
          <button type="button" className="ml-auto underline" onClick={toggleSatellite}>
            {satellite ? "Street map" : "Satellite"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
