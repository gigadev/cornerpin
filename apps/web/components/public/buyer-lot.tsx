"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import type { components } from "@/lib/api/schema";
import { isNetworkFailure } from "@/lib/inquiry-queue";

// The visitor's own activity on a lot page (P1-08). The page itself is the same for everyone
// and never reads the session; this asks the API from the browser instead, so the page can be
// cached later (P1-10) without ever holding anyone's data.

type BuyerLotState = components["schemas"]["BuyerLotState"];

export type BuyerLot =
  | { kind: "loading" }
  | { kind: "signed-out"; turnstileSiteKey: string | null }
  | { kind: "signed-in"; state: BuyerLotState }
  | { kind: "error" };

type Context = {
  lotId: string;
  signInHref: string;
  buyer: BuyerLot;
  reload: () => Promise<void>;
  setSaved: (saved: boolean) => void;
};

const BuyerLotContext = createContext<Context | null>(null);

export function useBuyerLot(): Context {
  const context = useContext(BuyerLotContext);
  if (!context) throw new Error("useBuyerLot needs a BuyerLotProvider");
  return context;
}

async function fetchBuyerLot(lotId: string): Promise<BuyerLot> {
  try {
    const { data, response } = await browserApi.GET("/v1/me/lots/{lot_id}", {
      params: { path: { lot_id: lotId } },
    });
    if (data) return { kind: "signed-in", state: data };
    if (response.status !== 401) return { kind: "error" };
    const providers = await browserApi.GET("/v1/auth/providers");
    return { kind: "signed-out", turnstileSiteKey: providers.data?.turnstile_site_key ?? null };
  } catch (failure) {
    // Offline (a page served from the cache): who's signed in can't be known, so the form
    // asks for an email and keeps the question until the connection returns (ADR-030).
    if (isNetworkFailure(failure)) return { kind: "signed-out", turnstileSiteKey: null };
    throw failure;
  }
}

export function BuyerLotProvider({
  lotId,
  lotPath,
  children,
}: {
  lotId: string;
  lotPath: string;
  children: ReactNode;
}) {
  const [buyer, setBuyer] = useState<BuyerLot>({ kind: "loading" });

  const reload = useCallback(async () => {
    setBuyer(await fetchBuyerLot(lotId));
  }, [lotId]);

  useEffect(() => {
    let cancelled = false;
    void fetchBuyerLot(lotId).then((loaded) => {
      if (!cancelled) setBuyer(loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [lotId]);

  const setSaved = useCallback((saved: boolean) => {
    setBuyer((current) =>
      current.kind === "signed-in" ? { ...current, state: { ...current.state, saved } } : current,
    );
  }, []);

  return (
    <BuyerLotContext.Provider
      value={{
        lotId,
        signInHref: `/signin?next=${encodeURIComponent(lotPath)}`,
        buyer,
        reload,
        setSaved,
      }}
    >
      {children}
    </BuyerLotContext.Provider>
  );
}

/** Save or unsave the lot; signed out, a link to sign in and come back. */
export function SaveLotButton() {
  const { lotId, signInHref, buyer, setSaved } = useBuyerLot();
  const [busy, setBusy] = useState(false);

  if (buyer.kind === "signed-out") {
    return (
      <Button asChild variant="outline" size="lg" className="h-10 px-4">
        <Link href={signInHref}>Save this lot</Link>
      </Button>
    );
  }
  if (buyer.kind !== "signed-in") return null;

  const saved = buyer.state.saved;
  async function toggle() {
    setBusy(true);
    const path = { params: { path: { lot_id: lotId } } };
    const { response } = saved
      ? await browserApi.DELETE("/v1/me/saved-lots/{lot_id}", path)
      : await browserApi.PUT("/v1/me/saved-lots/{lot_id}", path);
    if (response.ok) setSaved(!saved);
    setBusy(false);
  }

  return (
    <Button
      variant="outline"
      size="lg"
      className="h-10 px-4"
      aria-pressed={saved}
      disabled={busy}
      onClick={toggle}
    >
      {saved ? "Saved" : "Save this lot"}
    </Button>
  );
}
