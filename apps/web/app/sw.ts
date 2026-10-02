/// <reference lib="esnext" />
/// <reference lib="webworker" />
import type { PrecacheEntry, SerwistGlobalConfig, SerwistPlugin } from "serwist";
import {
  CacheFirst,
  CacheableResponsePlugin,
  ExpirationPlugin,
  NetworkOnly,
  Serwist,
  StaleWhileRevalidate,
} from "serwist";
import { CACHES, OFFLINE_PATH } from "../lib/pwa-caches";
import { isPublicPage, subdivisionOf } from "../lib/pwa-paths";
import { parsePushMessage, sameOriginUrl } from "../lib/push-message";

// The service worker (ADR-005, ADR-030). What it keeps:
// - public subdivision and lot pages, stale-while-revalidate; opening a lot also keeps its
//   subdivision page, which lists every lot with its shape;
// - public lot photos, cache-first, capped;
// - map tiles a visitor has actually seen, within OpenFreeMap's terms;
// - the app's static files and the offline page, precached at install.
// Nothing else is cached: not /app, /account, sign-in, or any API response other than public
// photos. Navigations it can't serve fall back to the offline page.

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}
declare const self: ServiceWorkerGlobalScope;

const DAY = 24 * 60 * 60;
const OPENFREEMAP = "https://tiles.openfreemap.org";

const ok = () => new CacheableResponsePlugin({ statuses: [200] });

/** Keep a lot's subdivision page whenever the lot page is kept. */
const keepSubdivisionPage: SerwistPlugin = {
  cacheDidUpdate: async ({ cacheName, request }) => {
    const parent = subdivisionOf(new URL(request.url).pathname);
    if (!parent) return;
    const cache = await caches.open(cacheName);
    const url = new URL(parent, self.location.origin).href;
    if (await cache.match(url)) return;
    const response = await fetch(url, { credentials: "omit" });
    if (response.status === 200) await cache.put(url, response);
  },
};

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  // A new version waits until the visitor accepts the update prompt (components/pwa).
  skipWaiting: false,
  clientsClaim: true,
  runtimeCaching: [
    {
      matcher: ({ request, url, sameOrigin }) =>
        sameOrigin &&
        isPublicPage(url.pathname) &&
        (request.destination === "document" || request.destination === "") &&
        request.headers.get("RSC") !== "1" &&
        !url.searchParams.has("_rsc"),
      handler: new StaleWhileRevalidate({
        cacheName: CACHES.pages,
        // Next varies pages on its router headers (RSC payload or HTML). Only HTML is kept
        // here, so a page kept from one kind of request serves any later navigation.
        matchOptions: { ignoreVary: true },
        plugins: [
          ok(),
          new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 30 * DAY }),
          keepSubdivisionPage,
        ],
      }),
    },
    {
      matcher: ({ url, sameOrigin }) =>
        sameOrigin &&
        (url.pathname.startsWith("/v1/public/photos/") ||
          (url.pathname === "/_next/image" &&
            (url.searchParams.get("url") ?? "").startsWith("/v1/public/photos/"))),
      handler: new CacheFirst({
        cacheName: CACHES.photos,
        plugins: [
          ok(),
          new ExpirationPlugin({
            maxEntries: 150,
            maxAgeSeconds: 30 * DAY,
            purgeOnQuotaError: true,
          }),
        ],
      }),
    },
    {
      // The site's fonts (ADR-033). Their names carry a hash, so a stored copy never goes stale.
      matcher: ({ url, sameOrigin }) =>
        sameOrigin && url.pathname.startsWith("/_next/static/media/") && url.pathname.endsWith(".woff2"),
      handler: new CacheFirst({
        cacheName: CACHES.fonts,
        plugins: [ok(), new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 365 * DAY })],
      }),
    },
    {
      // The style and the tile index change when OpenFreeMap updates; tiles, fonts and sprites
      // under a versioned path don't.
      matcher: ({ url }) =>
        url.origin === OPENFREEMAP &&
        (url.pathname.startsWith("/styles/") || url.pathname === "/planet"),
      handler: new StaleWhileRevalidate({
        cacheName: CACHES.mapStyle,
        plugins: [ok(), new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 30 * DAY })],
      }),
    },
    {
      matcher: ({ url }) => url.origin === OPENFREEMAP,
      handler: new CacheFirst({
        cacheName: CACHES.mapTiles,
        plugins: [
          ok(),
          new ExpirationPlugin({
            maxEntries: 600,
            maxAgeSeconds: 30 * DAY,
            purgeOnQuotaError: true,
          }),
        ],
      }),
    },
    {
      // Every other page is fetched as usual, with the offline page when that fails.
      matcher: ({ request, sameOrigin }) => sameOrigin && request.mode === "navigate",
      handler: new NetworkOnly(),
    },
  ],
  fallbacks: {
    entries: [{ url: OFFLINE_PATH, matcher: ({ request }) => request.destination === "document" }],
  },
});

serwist.addEventListeners();

// Saved-lot alerts (ADR-029). The API sends { title, body, url }.
self.addEventListener("push", (event) => {
  let payload: unknown = null;
  try {
    payload = event.data?.json();
  } catch {
    return;
  }
  const message = parsePushMessage(payload);
  if (!message) return;
  event.waitUntil(
    self.registration.showNotification(message.title, {
      body: message.body,
      icon: "/icons/icon-192.png",
      data: { url: message.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data: unknown = event.notification.data;
  const url = typeof data === "object" && data !== null && "url" in data ? data.url : null;
  event.waitUntil(self.clients.openWindow(sameOriginUrl(url, self.location.origin)));
});
