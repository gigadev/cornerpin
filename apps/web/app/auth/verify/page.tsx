import type { Metadata } from "next";
import Link from "next/link";
import { SiteHeader } from "@/components/site-header";
import { VerifyForm } from "./verify-form";

export const metadata: Metadata = { title: "Sign in · Cornerpin", robots: { index: false } };

// The link does not sign in on its own: mail scanners open links, and a GET would spend the
// single-use token before the person clicks. Signing in takes a click (ADR-023).
export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-md px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in to Cornerpin</h1>
        {token ? (
          <VerifyForm token={token} />
        ) : (
          <p className="mt-4">
            This link is incomplete. <Link href="/signin" className="underline">Request a new one</Link>.
          </p>
        )}
      </main>
    </>
  );
}
