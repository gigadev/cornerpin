import type { Metadata } from "next";
import { CachedLots } from "@/components/pwa/cached-lots";
import { SiteHeader } from "@/components/site-header";

// Shown by the service worker for a page it can't fetch or serve from its cache (ADR-030).
// Precached at install, so it must not depend on anything per request.
export const dynamic = "force-static";
export const metadata: Metadata = { title: "Offline · Cornerpin", robots: { index: false } };

export default function OfflinePage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto grid max-w-3xl gap-4 px-4 py-8">
        <h1 className="text-2xl font-semibold tracking-tight">You&apos;re offline</h1>
        <p className="text-muted-foreground">
          This page isn&apos;t saved on this device. These are, and open without a connection:
        </p>
        <CachedLots />
      </main>
    </>
  );
}
