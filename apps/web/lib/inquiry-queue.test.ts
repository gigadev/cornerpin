import { beforeEach, describe, expect, it } from "vitest";
import { isNetworkFailure, queueInquiry, queuedInquiries, removeQueued } from "./inquiry-queue";

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  const events: string[] = [];
  Object.assign(globalThis, {
    window: {
      localStorage: {
        getItem: (key: string) => store.get(key) ?? null,
        setItem: (key: string, value: string) => store.set(key, value),
        removeItem: (key: string) => store.delete(key),
      },
      dispatchEvent: (event: Event) => events.push(event.type),
    },
  });
});

const question = {
  lotId: "lot-7",
  lotLabel: "Lot 7, Juniper Bench",
  signedIn: false,
  name: "Pat",
  email: "pat@example.test",
  phone: null,
  message: "Is the well shared?",
  contact: null,
};

describe("the offline inquiry queue", () => {
  it("keeps questions in order until they are removed", () => {
    expect(queueInquiry(question)).toBe(true);
    expect(queueInquiry({ ...question, message: "And the road?" })).toBe(true);
    const [first, second] = queuedInquiries();
    expect([first?.message, second?.message]).toEqual(["Is the well shared?", "And the road?"]);

    removeQueued(first?.id ?? "");
    expect(queuedInquiries().map((item) => item.message)).toEqual(["And the road?"]);
    removeQueued(second?.id ?? "");
    expect(store.size).toBe(0);
  });

  it("ignores anything in storage that isn't a queued question", () => {
    store.set("cornerpin.queued-inquiries", '[{"id": 3}, "nonsense"]');
    expect(queuedInquiries()).toEqual([]);
    store.set("cornerpin.queued-inquiries", "{not json");
    expect(queuedInquiries()).toEqual([]);
  });

  it("recognises a failed connection", () => {
    expect(isNetworkFailure(new TypeError("Failed to fetch"))).toBe(true);
    expect(isNetworkFailure(new Error("400"))).toBe(false);
  });
});
