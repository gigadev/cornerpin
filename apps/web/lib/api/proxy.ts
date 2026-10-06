// Forwarding rules for the /v1 proxy (app/v1/[...path]/route.ts). The API stays on its own
// service; the browser only ever talks to the web origin, so the session cookie is first-party
// (ADR-006, ADR-023).

// svix-* sign inbound-email webhooks (ADR-037); the API checks them against the raw body.
const REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "origin",
  "user-agent",
  "svix-id",
  "svix-timestamp",
  "svix-signature",
] as const;
const RESPONSE_HEADERS = [
  "cache-control",
  "content-disposition",
  "content-type",
  "location",
] as const;

export function apiBaseUrl(): string {
  return process.env.API_BASE_URL ?? "http://localhost:8000";
}

export function forwardRequestHeaders(incoming: Headers, clientIp: string | null): Headers {
  const headers = new Headers();
  for (const name of REQUEST_HEADERS) {
    const value = incoming.get(name);
    if (value) headers.set(name, value);
  }
  const forwardedFor = incoming.get("x-forwarded-for") ?? clientIp;
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  return headers;
}

export function forwardResponseHeaders(upstream: Headers): Headers {
  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.get(name);
    if (value) headers.set(name, value);
  }
  for (const cookie of upstream.getSetCookie()) {
    headers.append("set-cookie", cookie);
  }
  // API responses are per-user; never let a cache keep them.
  if (!headers.has("cache-control")) headers.set("cache-control", "no-store");
  return headers;
}
