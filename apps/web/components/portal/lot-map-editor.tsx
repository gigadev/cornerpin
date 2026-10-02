"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import type { Polygon } from "geojson";
import type { ImageSource, Map as MapLibreMap, MapLayerMouseEvent, Marker } from "maplibre-gl";
import type { TerraDraw } from "terra-draw";
import { loadMapLibre } from "@/lib/map/load-maplibre";
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  LOTS_FILL,
  addLotLayers,
  fitToLots,
  hideLot,
  setLots,
} from "@/components/map/lot-layers";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { uploadOverlay } from "@/lib/api/upload";
import { formatAcres, statusLabel } from "@/lib/format";
import { STATUS_COLORS, STREET_STYLE, firstPolygon, lotFeatures, satelliteStyle } from "@/lib/map/lots";
import { FormMessage } from "./field";

type SubdivisionMap = components["schemas"]["SubdivisionMap"];
type MapLot = components["schemas"]["MapLot"];
type Corners = [[number, number], [number, number], [number, number], [number, number]];
type Mode = "idle" | "drawing" | "editing" | "aligning";

const OVERLAY_SOURCE = "overlay";
const OVERLAY_LAYER = "overlay";

function asCorners(corners: number[][]): Corners {
  const pairs = corners.map(([lng = 0, lat = 0]) => [lng, lat] as [number, number]);
  return [pairs[0] ?? [0, 0], pairs[1] ?? [0, 0], pairs[2] ?? [0, 0], pairs[3] ?? [0, 0]];
}

/** The owner's map: draw and edit lot boundaries, and line up a plat image to trace over
 * (P1-06, ADR-026). Shapes are saved one lot at a time; acreage follows from the shape. */
export function LotMapEditor({
  tenantId,
  subdivisionId,
  initial,
  satelliteKey,
}: {
  tenantId: string;
  subdivisionId: string;
  initial: SubdivisionMap;
  satelliteKey: string | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const cornersRef = useRef<Corners | null>(initial.overlay ? asCorners(initial.overlay.corners) : null);

  const [data, setData] = useState<SubdivisionMap>(initial);
  const [ready, setReady] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [hasShape, setHasShape] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opacity, setOpacity] = useState(initial.overlay?.opacity ?? 0.6);
  const [satellite, setSatellite] = useState(false);

  const collection = useMemo(() => lotFeatures(data.lots), [data.lots]);
  // Map event handlers outlive renders, so they read the latest values through refs.
  const collectionRef = useRef(collection);
  const overlayRef = useRef(data.overlay);
  const modeRef = useRef<Mode>("idle");
  useEffect(() => {
    collectionRef.current = collection;
    overlayRef.current = data.overlay;
    modeRef.current = mode;
  }, [collection, data.overlay, mode]);

  const selected: MapLot | undefined = data.lots.find((lot) => lot.id === selectedId);

  const addOverlay = useCallback((map: MapLibreMap) => {
    const overlay = overlayRef.current;
    if (!overlay || map.getSource(OVERLAY_SOURCE)) return;
    map.addSource(OVERLAY_SOURCE, {
      type: "image",
      url: overlay.url,
      coordinates: cornersRef.current ?? asCorners(overlay.corners),
    });
    map.addLayer(
      {
        id: OVERLAY_LAYER,
        type: "raster",
        source: OVERLAY_SOURCE,
        paint: { "raster-opacity": overlay.opacity, "raster-fade-duration": 0 },
      },
      map.getLayer(LOTS_FILL) ? LOTS_FILL : undefined,
    );
  }, []);

  // Create the map and the drawing tool once.
  const [lng, lat] = initial.center;
  useEffect(() => {
    let cancelled = false;
    let map: MapLibreMap | null = null;
    void Promise.all([
      loadMapLibre(),
      import("terra-draw"),
      import("terra-draw-maplibre-gl-adapter"),
    ]).then(([maplibre, terra, adapter]) => {
      if (cancelled || !container.current) return;
      map = new maplibre.Map({
        container: container.current,
        style: STREET_STYLE,
        center: [lng ?? 0, lat ?? 0],
        zoom: 16,
        attributionControl: { compact: true },
      });
      mapRef.current = map;
      const current = map;
      current.on("style.load", () => {
        addLotLayers(current, collectionRef.current);
        addOverlay(current);
      });
      current.once("load", () => {
        fitToLots(current, collectionRef.current);
        const draw = new terra.TerraDraw({
          adapter: new adapter.TerraDrawMapLibreGLAdapter({ map: current }),
          modes: [
            new terra.TerraDrawPolygonMode({
              validation: (feature) =>
                terra.ValidateNotSelfIntersecting(feature),
            }),
            new terra.TerraDrawSelectMode({
              flags: {
                polygon: {
                  feature: {
                    draggable: true,
                    coordinates: { draggable: true, midpoints: true, deletable: true },
                  },
                },
              },
            }),
          ],
        });
        draw.start();
        draw.on("finish", (id) => {
          setHasShape(true);
          // Straight into adjusting the finished shape.
          draw.setMode("select");
          draw.selectFeature(id);
        });
        drawRef.current = draw;
        setReady(true);
      });
      current.on("click", LOTS_FILL, (event: MapLayerMouseEvent) => {
        if (modeRef.current !== "idle") return;
        const id: unknown = event.features?.[0]?.properties["id"];
        if (typeof id === "string") setSelectedId(id);
      });
    });
    return () => {
      cancelled = true;
      drawRef.current?.stop();
      drawRef.current = null;
      map?.remove();
      mapRef.current = null;
    };
  }, [lng, lat, addOverlay]);

  // Keep the static lot layers in step with the data.
  useEffect(() => {
    if (mapRef.current && ready) setLots(mapRef.current, collection);
  }, [collection, ready]);

  async function reload() {
    const { data: fresh } = await browserApi.GET(
      "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/map",
      { params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } } },
    );
    if (fresh) setData(fresh);
  }

  function resetDrawing() {
    const draw = drawRef.current;
    if (draw) {
      draw.setMode("static");
      draw.clear();
    }
    if (mapRef.current) hideLot(mapRef.current, null);
    setHasShape(false);
    setMode("idle");
  }

  function startDrawing() {
    const draw = drawRef.current;
    if (!draw || !selected || !mapRef.current) return;
    setError(null);
    setMessage(null);
    draw.clear();
    hideLot(mapRef.current, selected.id);
    draw.setMode("polygon");
    setHasShape(false);
    setMode("drawing");
  }

  function startEditing() {
    const draw = drawRef.current;
    const polygon = selected?.boundary ? firstPolygon(selected.boundary) : null;
    if (!draw || !selected || !polygon || !mapRef.current) return;
    setError(null);
    setMessage(
      selected.boundary && selected.boundary.coordinates.length > 1
        ? "This lot's shape has several parts; saving keeps only the first."
        : null,
    );
    draw.clear();
    hideLot(mapRef.current, selected.id);
    const id = crypto.randomUUID();
    draw.addFeatures([{ id, type: "Feature", geometry: polygon, properties: { mode: "polygon" } }]);
    draw.setMode("select");
    draw.selectFeature(id);
    setHasShape(true);
    setMode("editing");
  }

  async function saveShape() {
    const draw = drawRef.current;
    if (!draw || !selected) return;
    const shape = draw.getSnapshot().find((feature) => feature.geometry.type === "Polygon");
    if (!shape) {
      setError("Draw the shape first: click each corner, then press Enter.");
      return;
    }
    const boundary: Polygon = { type: "Polygon", coordinates: (shape.geometry as Polygon).coordinates };
    const { data: saved, error: failure } = await browserApi.PUT(
      "/v1/tenants/{tenant_id}/lots/{lot_id}/boundary",
      { params: { path: { tenant_id: tenantId, lot_id: selected.id } }, body: { boundary } },
    );
    if (!saved) {
      setError(errorMessage(failure));
      return;
    }
    resetDrawing();
    await reload();
    setMessage(
      `Saved lot ${selected.number}: ${formatAcres(saved.acreage)}.` +
        (saved.overlaps.length > 0
          ? ` It overlaps lot ${saved.overlaps.join(", ")}; check the lines.`
          : ""),
    );
  }

  async function removeShape() {
    if (!selected || !window.confirm(`Remove lot ${selected.number}'s shape?`)) return;
    const { error: failure } = await browserApi.DELETE(
      "/v1/tenants/{tenant_id}/lots/{lot_id}/boundary",
      { params: { path: { tenant_id: tenantId, lot_id: selected.id } } },
    );
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    await reload();
    setMessage(`Removed lot ${selected.number}'s shape.`);
  }

  // --- plat overlay ------------------------------------------------------------------------

  function overlaySource(): ImageSource | undefined {
    return mapRef.current?.getSource<ImageSource>(OVERLAY_SOURCE);
  }

  async function onOverlayFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    setMessage("Uploading the plat…");
    const result = await uploadOverlay(tenantId, subdivisionId, file);
    if (!result.ok) {
      setMessage(null);
      setError(result.error);
      return;
    }
    cornersRef.current = asCorners(result.value.corners);
    // A new query string so the map fetches the new image rather than a cached earlier one.
    overlayRef.current = { ...result.value, url: `${result.value.url}?v=${Date.now()}` };
    setData((current) => ({ ...current, overlay: overlayRef.current }));
    setOpacity(result.value.opacity);
    // If the map is still loading, its style.load handler draws the overlay from overlayRef.
    const map = mapRef.current;
    if (map?.isStyleLoaded()) {
      if (map.getLayer(OVERLAY_LAYER)) map.removeLayer(OVERLAY_LAYER);
      if (map.getSource(OVERLAY_SOURCE)) map.removeSource(OVERLAY_SOURCE);
      addOverlay(map);
    }
    setMessage("Plat added. Use “Line up plat” to drag its corners into place.");
  }

  function startAligning() {
    const map = mapRef.current;
    const corners = cornersRef.current;
    if (!map || !corners) return;
    void loadMapLibre().then(({ Marker }) => {
      markersRef.current = corners.map((corner, index) => {
        const marker = new Marker({ draggable: true, color: "#1c1917" })
          .setLngLat(corner)
          .addTo(map);
        marker.getElement().setAttribute("aria-label", `Plat corner ${index + 1}`);
        marker.on("drag", () => {
          const next = [...(cornersRef.current ?? corners)] as Corners;
          const { lng: x, lat: y } = marker.getLngLat();
          next[index] = [x, y];
          cornersRef.current = next;
          overlaySource()?.setCoordinates(next);
        });
        return marker;
      });
    });
    setMode("aligning");
    setMessage("Drag the four pins so the plat's lot lines sit on the map, then save.");
  }

  function stopAligning() {
    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];
    setMode("idle");
  }

  async function saveOverlay() {
    const { data: saved, error: failure } = await browserApi.PATCH(
      "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/overlay",
      {
        params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
        body: { corners: cornersRef.current ?? undefined, opacity },
      },
    );
    if (!saved) {
      setError(errorMessage(failure));
      return;
    }
    stopAligning();
    setMessage("Plat position saved.");
  }

  function cancelAligning() {
    stopAligning();
    const original = overlayRef.current ? asCorners(overlayRef.current.corners) : null;
    cornersRef.current = original;
    if (original) overlaySource()?.setCoordinates(original);
    setMessage(null);
  }

  function onOpacity(value: number) {
    setOpacity(value);
    if (mapRef.current?.getLayer(OVERLAY_LAYER)) {
      mapRef.current.setPaintProperty(OVERLAY_LAYER, "raster-opacity", value);
    }
  }

  async function removeOverlay() {
    if (!window.confirm("Remove the plat image?")) return;
    const { error: failure } = await browserApi.DELETE(
      "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/overlay",
      { params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } } },
    );
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    const map = mapRef.current;
    if (map?.getLayer(OVERLAY_LAYER)) map.removeLayer(OVERLAY_LAYER);
    if (map?.getSource(OVERLAY_SOURCE)) map.removeSource(OVERLAY_SOURCE);
    cornersRef.current = null;
    overlayRef.current = null;
    setData((current) => ({ ...current, overlay: null }));
    setMessage("Plat removed.");
  }

  function toggleSatellite() {
    if (!satelliteKey || !mapRef.current) return;
    const next = !satellite;
    mapRef.current.setStyle(next ? satelliteStyle(satelliteKey) : STREET_STYLE);
    setSatellite(next);
  }

  const busy = mode !== "idle";
  const drawnCount = data.lots.filter((lot) => lot.boundary).length;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
      <div className="grid gap-2">
        <div
          ref={container}
          role="region"
          aria-label="Map editor"
          data-ready={ready ? "true" : "false"}
          className="h-[65vh] min-h-96 w-full overflow-hidden rounded-lg border border-border"
        />
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {mode === "drawing" ? (
            <span>Click each corner of the lot, then press Enter (or click the first corner).</span>
          ) : mode === "editing" ? (
            <span>Drag corners to move them; drag a midpoint to add one.</span>
          ) : (
            <span className="text-muted-foreground">
              {drawnCount} of {data.lots.length} lots have a shape. Click a lot to select it.
            </span>
          )}
          {satelliteKey ? (
            <button type="button" className="ml-auto underline" onClick={toggleSatellite}>
              {satellite ? "Street map" : "Satellite"}
            </button>
          ) : null}
        </div>
        <FormMessage error={error} success={message} />
      </div>

      <div className="grid content-start gap-4">
        <section aria-labelledby="selected-lot" className="grid gap-2 rounded-lg border border-border p-3">
          <h2 id="selected-lot" className="font-medium">
            {selected ? `Lot ${selected.number}` : "No lot selected"}
          </h2>
          {selected ? (
            <>
              <p className="text-sm text-muted-foreground">
                {statusLabel(selected.status)} · {formatAcres(selected.acreage)}
                {selected.boundary ? "" : " · no shape yet"}
              </p>
              {mode === "drawing" || mode === "editing" ? (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" onClick={saveShape} disabled={!hasShape}>
                    Save shape
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={resetDrawing}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" onClick={startDrawing} disabled={!ready || busy}>
                    {selected.boundary ? "Redraw shape" : "Draw shape"}
                  </Button>
                  {selected.boundary ? (
                    <>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={startEditing}
                        disabled={!ready || busy}
                      >
                        Edit shape
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={removeShape}
                        disabled={busy}
                      >
                        Remove shape
                      </Button>
                    </>
                  ) : null}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Pick one below or on the map.</p>
          )}
        </section>

        <section aria-labelledby="plat-overlay" className="grid gap-2 rounded-lg border border-border p-3">
          <h2 id="plat-overlay" className="font-medium">
            Plat image
          </h2>
          {data.overlay ? (
            <>
              <div className="grid gap-1">
                <Label htmlFor="plat-opacity">See-through: {Math.round((1 - opacity) * 100)}%</Label>
                <input
                  id="plat-opacity"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={opacity}
                  onChange={(event) => onOpacity(Number(event.target.value))}
                />
              </div>
              {mode === "aligning" ? (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" onClick={saveOverlay}>
                    Save plat position
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={cancelAligning}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button type="button" size="sm" variant="outline" onClick={startAligning} disabled={busy}>
                    Line up plat
                  </Button>
                  <Button type="button" size="sm" variant="outline" onClick={saveOverlay} disabled={busy}>
                    Save see-through
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={removeOverlay} disabled={busy}>
                    Remove plat
                  </Button>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Add an image of the plat to trace lots over. A PDF plat can be saved as an image first.
            </p>
          )}
          <Label htmlFor="plat-file" className="mt-1">
            {data.overlay ? "Replace plat image" : "Add plat image"}
          </Label>
          <input
            id="plat-file"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={onOverlayFile}
            disabled={busy}
            className="text-sm"
          />
        </section>

        <section aria-labelledby="lot-list" className="grid gap-1">
          <h2 id="lot-list" className="font-medium">
            Lots
          </h2>
          <ul className="max-h-80 overflow-y-auto rounded-lg border border-border">
            {data.lots.map((lot) => (
              <li key={lot.id}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setSelectedId(lot.id)}
                  aria-pressed={lot.id === selectedId}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-muted aria-pressed:bg-muted"
                >
                  <span
                    aria-hidden
                    className="inline-block size-2.5 rounded-full"
                    style={{ backgroundColor: STATUS_COLORS[lot.status] }}
                  />
                  <span className="font-medium">Lot {lot.number}</span>
                  <span className="ml-auto text-muted-foreground">
                    {lot.boundary ? "shape" : "no shape"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
