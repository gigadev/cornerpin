// MapLibre needs a browser, so it is imported on demand from client effects, never during the
// server render. Its worker is served from public/maplibre (scripts/copy-maplibre-worker.mjs).

export const MAPLIBRE_WORKER_URL = "/maplibre/maplibre-gl-worker.mjs";

export async function loadMapLibre(): Promise<typeof import("maplibre-gl")> {
  const maplibre = await import("maplibre-gl");
  maplibre.setWorkerUrl(MAPLIBRE_WORKER_URL);
  return maplibre;
}
