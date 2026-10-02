import Link from "next/link";
import { SiteHeader } from "@/components/site-header";

// An unknown code, or a lot that isn't published right now. Says nothing about which.
export default function QrNotFound() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto grid max-w-md gap-3 px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">
          This lot isn&apos;t listed right now
        </h1>
        <p className="text-muted-foreground">
          The sign you scanned points to a lot that isn&apos;t on Cornerpin at the moment. It may
          be coming soon, or no longer for sale.
        </p>
        <p>
          <Link href="/" className="underline">
            Go to Cornerpin
          </Link>
        </p>
      </main>
    </>
  );
}
