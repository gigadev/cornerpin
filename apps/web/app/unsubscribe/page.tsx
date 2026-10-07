import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { serverApi } from "@/lib/api/server";
import { channelLabel } from "@/lib/format";
import { StopButton } from "./stop-button";

// Where the link in an owner's outreach email lands (P2-03, ADR-036). Opening it changes
// nothing, because mail scanners open links; the button records the opt-out.

const CARD =
  "mx-auto grid max-w-md gap-4 rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8";

export const metadata: Metadata = { title: "Unsubscribe · Cornerpin", robots: { index: false } };

export default async function UnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token = "" } = await searchParams;
  const api = await serverApi();
  const { data } = token
    ? await api.GET("/v1/unsubscribe", { params: { query: { token } } })
    : { data: undefined };

  return (
    <>
      <SiteHeader />
      <main className="contours min-h-[calc(100dvh-4rem)] px-4 py-10 sm:py-16">
        <div className={CARD}>
          <h1 className="text-3xl font-semibold tracking-tight">Unsubscribe</h1>
          {data ? (
            <StopButton
              token={token}
              tenantName={data.tenant_name}
              channel={channelLabel(data.channel).toLowerCase()}
              allowed={data.allowed}
            />
          ) : (
            <p>
              This link doesn&apos;t work; it may have been cut short. You can choose who may
              contact you on <Link href="/account" className="underline">your account page</Link>.
            </p>
          )}
        </div>
      </main>
    </>
  );
}
