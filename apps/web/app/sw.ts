/// <reference lib="esnext" />
/// <reference lib="webworker" />
import { Serwist } from "serwist";
import { parsePushMessage, sameOriginUrl } from "../lib/push-message";

declare const self: ServiceWorkerGlobalScope;

// Deliberately no precache and no runtime caching yet. The caching rules, offline fallback
// and queued inquiries arrive in P1-10, and authenticated responses (/app, /account, /v1/me/*)
// are never cached.
const serwist = new Serwist({
  skipWaiting: true,
  clientsClaim: true,
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
