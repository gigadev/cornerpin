import Link from "next/link";
import { SignOutButton } from "@/components/sign-out-button";
import { SiteHeader } from "@/components/site-header";
import { buttonVariants } from "@/components/ui/button";
import { getMe } from "@/lib/api/server";
import { cn } from "@/lib/utils";

const HERO_BUTTON = "h-11 px-5 text-base";

const POINTS = [
  ["See what's left", "Every lot on the map, coloured by status, with price, size and photos."],
  ["Scan the sign", "Standing on a lot? The QR code on its sign opens the lot's page."],
  ["Hear when it changes", "Save the lots you like and get an email when their price or status changes."],
] as const;

export default async function HomePage() {
  const me = await getMe();

  return (
    <>
      <SiteHeader>
        {me ? (
          <>
            <span className="hidden text-muted-foreground sm:inline">{me.email}</span>
            {me.memberships.length > 0 ? (
              <Link href="/app">Owner portal</Link>
            ) : null}
            <Link href="/account">Your account</Link>
            <SignOutButton />
          </>
        ) : (
          <Link href="/signin">Sign in</Link>
        )}
      </SiteHeader>
      <main>
        <section className="contours border-b border-border">
          <div className="mx-auto grid max-w-5xl gap-5 px-4 py-16 sm:py-24">
            <p className="text-sm font-medium tracking-wide text-primary uppercase">
              Land for sale, lot by lot
            </p>
            <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Subdivision lots, on the map
            </h1>
            <p className="max-w-prose text-lg text-muted-foreground">
              Browse lots by status and price, see where they are, and look through photos and
              documents.
            </p>
            <div className="flex flex-wrap gap-3 pt-2">
              <Link href="/juniper-bench" className={cn(buttonVariants({ size: "lg" }), HERO_BUTTON)}>
                See a demo subdivision
              </Link>
              <Link href="/help" className={cn(buttonVariants({ size: "lg", variant: "outline" }), HERO_BUTTON)}>
                How it works
              </Link>
            </div>
          </div>
        </section>
        <ul className="mx-auto grid max-w-5xl gap-4 px-4 py-12 sm:grid-cols-3">
          {POINTS.map(([title, text]) => (
            <li key={title} className="grid content-start gap-2 rounded-xl border border-border bg-card p-5">
              <h2 className="text-lg font-semibold">{title}</h2>
              <p className="text-sm text-muted-foreground">{text}</p>
            </li>
          ))}
        </ul>
      </main>
    </>
  );
}
