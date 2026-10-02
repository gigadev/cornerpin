import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import {
  AlertsForm,
  ConsentList,
  ProfileForm,
  SavedLotRemove,
} from "@/components/account/account-forms";
import { StatusBadge } from "@/components/portal/status-badge";
import { SignOutButton } from "@/components/sign-out-button";
import { SiteHeader } from "@/components/site-header";
import { getMe, serverApi } from "@/lib/api/server";
import { formatPrice } from "@/lib/format";

// A buyer's account (P1-08). Private: never cached by the service worker (ADR-005).
export const metadata: Metadata = { title: "Your account · Cornerpin", robots: { index: false } };

const DEFAULT_TIME_ZONE = "America/Boise";

export default async function AccountPage() {
  const me = await getMe();
  if (!me) redirect("/signin?next=/account");

  const api = await serverApi();
  const [saved, prefs, consents] = await Promise.all([
    api.GET("/v1/me/saved-lots"),
    api.GET("/v1/me/notification-prefs"),
    api.GET("/v1/me/consents"),
  ]);
  if (!saved.data || !prefs.data || !consents.data) throw new Error("Could not load the account");

  return (
    <>
      <SiteHeader>
        {me.memberships.length > 0 ? (
          <Link href="/app">Owner portal</Link>
        ) : null}
        <SignOutButton />
      </SiteHeader>
      <main className="mx-auto grid max-w-3xl gap-8 px-4 py-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your account</h1>
          <p className="mt-1 text-muted-foreground">Signed in as {me.email}</p>
        </div>

        <section aria-labelledby="saved-heading" className="grid gap-3">
          <h2 id="saved-heading" className="text-xl font-semibold tracking-tight">
            Saved lots
          </h2>
          {saved.data.length === 0 ? (
            <p className="text-muted-foreground">
              Nothing saved yet. Use &ldquo;Save this lot&rdquo; on a lot page to follow it here.
            </p>
          ) : (
            <ul className="divide-y divide-border rounded-xl border border-border bg-card">
              {saved.data.map((lot) => (
                <li key={lot.lot_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <Link
                    href={`/${lot.subdivision_slug}/lots/${encodeURIComponent(lot.number)}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    Lot {lot.number}, {lot.subdivision_name}
                  </Link>
                  <StatusBadge status={lot.status} />
                  <span className="tabular-nums text-muted-foreground">
                    {formatPrice(lot.price)}
                  </span>
                  <span className="ml-auto">
                    <SavedLotRemove lotId={lot.lot_id} number={lot.number} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section aria-labelledby="alerts-heading" className="grid gap-3">
          <h2 id="alerts-heading" className="text-xl font-semibold tracking-tight">
            Alerts
          </h2>
          <AlertsForm prefs={prefs.data} />
        </section>

        <section aria-labelledby="contact-heading" className="grid gap-3">
          <h2 id="contact-heading" className="text-xl font-semibold tracking-tight">
            Who may contact you
          </h2>
          {consents.data.length === 0 ? (
            <p className="text-muted-foreground">
              No owner has your permission to contact you beyond replying to your messages. You
              can give it when you contact an owner from a lot page.
            </p>
          ) : (
            <ConsentList
              consents={consents.data}
              timeZone={me.time_zone ?? DEFAULT_TIME_ZONE}
            />
          )}
        </section>

        <section aria-labelledby="details-heading" className="grid gap-3">
          <h2 id="details-heading" className="text-xl font-semibold tracking-tight">
            Your details
          </h2>
          <ProfileForm me={me} />
        </section>
      </main>
    </>
  );
}
