// Shared by the service worker and its tests: what a saved-lot push carries (ADR-029).

export type PushMessage = { title: string; body: string; url: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** The push payload, if it has the expected shape. */
export function parsePushMessage(value: unknown): PushMessage | null {
  if (!isRecord(value)) return null;
  const { title, body, url } = value;
  if (typeof title !== "string" || typeof body !== "string" || typeof url !== "string") {
    return null;
  }
  return { title, body, url };
}

/** Where a notification click may go: a page on this site, never anywhere else. */
export function sameOriginUrl(url: unknown, origin: string): string {
  if (typeof url !== "string") return origin;
  try {
    const target = new URL(url, origin);
    return target.origin === origin ? target.href : origin;
  } catch {
    return origin;
  }
}

/** A VAPID public key (base64url) as the bytes `pushManager.subscribe` wants. */
export function applicationServerKey(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}
