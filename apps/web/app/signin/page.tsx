import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { getMe, serverApi } from "@/lib/api/server";
import { signInDestination } from "@/lib/safe-next";
import { SignInForm } from "./sign-in-form";

export const metadata: Metadata = { title: "Sign in · Cornerpin", robots: { index: false } };

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { next, error } = await searchParams;
  const nextPath = signInDestination(next);
  // Already signed in: go on to the destination, which is never this page or the home page.
  if (await getMe()) redirect(nextPath);

  const api = await serverApi();
  const { data: providers } = await api.GET("/v1/auth/providers");
  if (!providers) throw new Error("Could not load sign-in options");

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-md px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-2 text-muted-foreground">
          We&apos;ll email you a link. No password needed; a new address gets a new account.
        </p>
        {error === "google" ? (
          <p role="alert" className="mt-4 rounded border border-border bg-card p-3 text-sm">
            Google sign-in didn&apos;t complete. Try again, or use an email link.
          </p>
        ) : null}
        <SignInForm
          nextPath={nextPath}
          turnstileSiteKey={providers.turnstile_site_key}
          googleEnabled={providers.google}
        />
        <p className="mt-8 text-sm text-muted-foreground">
          New here?{" "}
          <Link href="/help" className="underline">
            See how Cornerpin works
          </Link>
          .
        </p>
      </main>
    </>
  );
}
