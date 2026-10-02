import Link from "next/link";
import { SignOutButton } from "@/components/sign-out-button";
import { SiteHeader } from "@/components/site-header";
import { getMe } from "@/lib/api/server";

export default async function HomePage() {
  const me = await getMe();

  return (
    <>
      <SiteHeader>
        {me ? (
          <>
            <span className="hidden text-muted-foreground sm:inline">{me.email}</span>
            {me.memberships.length > 0 ? (
              <Link href="/app" className="underline">
                Owner portal
              </Link>
            ) : null}
            <Link href="/account" className="underline">
              Your account
            </Link>
            <SignOutButton />
          </>
        ) : (
          <Link href="/signin" className="underline">
            Sign in
          </Link>
        )}
      </SiteHeader>
      <main className="mx-auto max-w-5xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Subdivision lots, on the map
        </h1>
        <p className="mt-3 max-w-prose text-muted-foreground">
          Browse lots by status and price, see where they are, and look through photos and
          documents.
        </p>
      </main>
    </>
  );
}
