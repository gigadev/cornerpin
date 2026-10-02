"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Turnstile } from "@/components/turnstile";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import {
  QUEUE_CHANGED,
  isNetworkFailure,
  queuedInquiries,
  removeQueued,
  type QueuedInquiry,
} from "@/lib/inquiry-queue";
import { useOnline } from "@/lib/use-online";

// Sends questions written offline once the connection returns, on whichever Cornerpin page is
// open (ADR-030). A signed-out visitor's question gets a fresh Turnstile check first.

type Outcome = { kind: "sent" | "failed"; text: string };

async function send(item: QueuedInquiry, token: string | null): Promise<Outcome | "offline"> {
  try {
    const { error } = await browserApi.POST("/v1/lots/{lot_id}/inquiries", {
      params: { path: { lot_id: item.lotId } },
      body: item.signedIn
        ? { name: item.name, phone: item.phone, message: item.message, contact: item.contact }
        : {
            name: item.name,
            email: item.email,
            phone: item.phone,
            message: item.message,
            turnstile_token: token,
          },
    });
    removeQueued(item.id);
    return error
      ? {
          kind: "failed",
          text: `Your question about ${item.lotLabel} couldn't be sent: ${errorMessage(error)}`,
        }
      : { kind: "sent", text: `Sent your question about ${item.lotLabel}.` };
  } catch (failure) {
    if (isNetworkFailure(failure)) return "offline";
    throw failure;
  }
}

export function QueuedInquiries() {
  const online = useOnline();
  const [items, setItems] = useState<QueuedInquiry[]>([]);
  const [siteKey, setSiteKey] = useState<string | null>(null);
  const inFlight = useRef(false);
  // Set when a send found no connection although the browser claimed one; cleared by the
  // next "online" event, so a weak signal doesn't cause a retry loop.
  const [stalled, setStalled] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    const load = () => setItems(queuedInquiries());
    const retry = () => setStalled(false);
    load();
    window.addEventListener(QUEUE_CHANGED, load);
    window.addEventListener("storage", load);
    window.addEventListener("online", retry);
    return () => {
      window.removeEventListener(QUEUE_CHANGED, load);
      window.removeEventListener("storage", load);
      window.removeEventListener("online", retry);
    };
  }, []);

  const next = items[0];

  const deliver = useCallback((item: QueuedInquiry, token: string | null) => {
    if (inFlight.current) return;
    inFlight.current = true;
    void send(item, token).then(
      (result) => {
        inFlight.current = false;
        if (result === "offline") setStalled(true);
        else setOutcome(result);
      },
      () => {
        inFlight.current = false;
        setStalled(true);
      },
    );
  }, []);

  const ready = online && !stalled;

  // Signed-in questions go as soon as the connection is back.
  useEffect(() => {
    if (ready && next?.signedIn) deliver(next, null);
  }, [ready, next, deliver]);

  // Signed-out ones need a Turnstile token, so the widget needs its site key.
  useEffect(() => {
    if (!online || !next || next.signedIn || siteKey) return;
    void browserApi
      .GET("/v1/auth/providers")
      .then(({ data }) => setSiteKey(data?.turnstile_site_key ?? null))
      .catch(() => undefined);
  }, [online, next, siteKey]);

  if (!next && !outcome) return null;

  return (
    <div
      role="status"
      className="grid gap-2 rounded-lg border border-border bg-card p-3 shadow-lg"
    >
      {next ? (
        <>
          <p className="text-sm">
            {online && !stalled
              ? `Sending your question about ${next.lotLabel}…`
              : `You're offline. Your question about ${next.lotLabel} will be sent when ` +
                "you're back online."}
          </p>
          {ready && !next.signedIn && siteKey ? (
            <Turnstile
              key={next.id}
              siteKey={siteKey}
              onToken={(token) => {
                if (token) deliver(next, token);
              }}
            />
          ) : null}
        </>
      ) : null}
      {outcome ? (
        <div className="flex items-center gap-3">
          <p className="text-sm" role={outcome.kind === "failed" ? "alert" : undefined}>
            {outcome.text}
          </p>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setOutcome(null)}>
            OK
          </Button>
        </div>
      ) : null}
    </div>
  );
}
