"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import type { MapLayerMouseEvent, Map as MapLibreMap } from "maplibre-gl";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { LOT_STATUSES, statusLabel } from "@/lib/format";
import { loadMapLibre } from "@/lib/map/load-maplibre";
import {
  STATUS_COLORS,
  STREET_STYLE,
  lotFeatures,
  satelliteStyle,
  type MapLotInput,
} from "@/lib/map/lots";
import { LOTS_FILL, LOTS_SOURCE, addLotLayers, fitToLots, renderedLotNumbers } from "./lot-layers";

const FOCUS_LAYER = "lot-focus";

/** The public map: published lots coloured by status (P1-06, P1-07). With `linkBase`, clicking
 * a lot opens its page; with `focusLotId`, the map frames that lot and outlines it. The page
 * around it lists the same lots, so nothing here is needed without JavaScript. */
export function PublicLotMap({
  center,
  lots,
  satelliteKey,
  linkBase,
  focusLotId,
  size = "tall",
}: {
  center: [number, number];
  lots: MapLotInput[];
  satelliteKey: string | null;
  linkBase?: string;
  focusLotId?: string;
  size?: "tall" | "short";
}) {
  const router = useRouter();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [rendered, setRendered] = useState("");
  const [satellite, setSatellite] = useState(false);
  const collection = useMemo(() => lotFeatures(lots), [lots]);
  const [lng, lat] = center;

  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    // Loaded on demand: MapLibre needs a browser, so it stays out of the server render.
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
      current.on("style.load", () => {
        addLotLayers(current, collection);
        if (focusLotId && !current.getLayer(FOCUS_LAYER)) {
          current.addLayer({
            id: FOCUS_LAYER,
            type: "line",
            source: LOTS_SOURCE,
            filter: ["==", ["get", "id"], focusLotId],
            paint: { "line-color": "#1c1917", "line-width": 4 },
          });
        }
      });
      current.once("load", () => {
        const focus = focusLotId
          ? { ...collection, features: collection.features.filter((f) => f.id === focusLotId) }
          : collection;
        // A single lot is framed a little wider, so its neighbours show too.
        fitToLots(current, focus.features.length > 0 ? focus : collection, {
          maxZoom: focusLotId ? 17 : 18,
        });
      });
      current.on("idle", () => setRendered(renderedLotNumbers(current)));
      if (linkBase) {
        current.on("click", LOTS_FILL, (event: MapLayerMouseEvent) => {
          const number: unknown = event.features?.[0]?.properties["number"];
          if (typeof number === "string") router.push(`${linkBase}${encodeURIComponent(number)}`);
        });
        current.on("mouseenter", LOTS_FILL, () => (current.getCanvas().style.cursor = "pointer"));
        current.on("mouseleave", LOTS_FILL, () => (current.getCanvas().style.cursor = ""));
      }
    });
    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
  }, [collection, lng, lat, focusLotId, linkBase, router]);

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
        className={`${size === "tall" ? "h-[55vh] min-h-80" : "h-72"} relative w-full overflow-hidden rounded-lg border border-border bg-muted`}
      >
        <noscript>
          <p className="p-4 text-sm text-muted-foreground">
            The map needs JavaScript. Every lot is listed on this page.
          </p>
        </noscript>
      </div>
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
