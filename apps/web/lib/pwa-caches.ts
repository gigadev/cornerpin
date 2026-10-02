// Names shared by the service worker and the pages that read its caches (ADR-030).

export const OFFLINE_PATH = "/offline";

export const CACHES = {
  pages: "pages",
  photos: "photos",
  mapStyle: "map-style",
  mapTiles: "map-tiles",
  fonts: "fonts",
} as const;
