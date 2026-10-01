import Link from "next/link";
import { SiteHeader } from "@/components/site-header";

export default function HomePage() {
  return (
    <>
      <SiteHeader>
        <Link href="/signin" className="underline">
          Sign in
        </Link>
      </SiteHeader>
      <main className="mx-auto max-w-5xl px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Subdivision lots, on the map
        </h1>
        <p className="mt-3 max-w-prose text-muted">
          Browse lots by status and price, see where they are, and look through photos and
          documents.
        </p>
      </main>
    </>
  );
}
