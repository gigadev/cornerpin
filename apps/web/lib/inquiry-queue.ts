// Questions written while offline (ADR-030). Kept in this browser's storage until they can be
// sent; QueuedInquiries (components/pwa) sends them when the connection returns. Not a
// service-worker background sync: a signed-out visitor's question needs a fresh Turnstile
// token, which only a page can get, and Safari has no background sync.

export type QueuedInquiry = {
  id: string;
  lotId: string;
  lotLabel: string; // "Lot 7, Juniper Bench"
  signedIn: boolean;
  name: string;
  email: string | null; // signed out only; signed in, the account's address is used
  phone: string | null;
  message: string;
  contact: { email: boolean; sms: boolean } | null; // signed in only
  queuedAt: string;
};

const KEY = "cornerpin.queued-inquiries";
export const QUEUE_CHANGED = "cornerpin:queued-inquiries";

function isQueuedInquiry(value: unknown): value is QueuedInquiry {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.id === "string" &&
    typeof item.lotId === "string" &&
    typeof item.lotLabel === "string" &&
    typeof item.signedIn === "boolean" &&
    typeof item.name === "string" &&
    typeof item.message === "string"
  );
}

export function queuedInquiries(): QueuedInquiry[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isQueuedInquiry) : [];
  } catch {
    return [];
  }
}

function save(items: QueuedInquiry[]): boolean {
  try {
    if (items.length === 0) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(items));
    window.dispatchEvent(new Event(QUEUE_CHANGED));
    return true;
  } catch {
    return false;
  }
}

/** Keep a question to send later. False if this browser won't store it. */
export function queueInquiry(item: Omit<QueuedInquiry, "id" | "queuedAt">): boolean {
  const queued: QueuedInquiry = {
    ...item,
    id: crypto.randomUUID(),
    queuedAt: new Date().toISOString(),
  };
  return save([...queuedInquiries(), queued]);
}

export function removeQueued(id: string): void {
  save(queuedInquiries().filter((item) => item.id !== id));
}

/** fetch() rejects with a TypeError when there is no connection at all. */
export function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError;
}
