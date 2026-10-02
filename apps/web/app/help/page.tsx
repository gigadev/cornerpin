import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/site-header";
import shots from "@/lib/walkthrough-shots.json";

// The in-app guide: a tour of Cornerpin for buyers and owners, with screenshots of the demo
// subdivision. The developer version, with running it locally, is docs/WALKTHROUGH.md; both use
// the screenshots in public/walkthrough/, retaken with `pnpm --filter web walkthrough`.

export const dynamic = "force-static";
export const metadata: Metadata = {
  title: "How Cornerpin works",
  description: "A tour of Cornerpin: finding a lot, asking the owner, saved-lot alerts and signs.",
  alternates: { canonical: "/help" },
};

type ShotName = keyof typeof shots;

const SECTIONS = [
  ["finding", "Finding a lot"],
  ["asking", "Asking the owner"],
  ["account", "Your account"],
  ["signs", "Signs on the lots"],
  ["offline", "With a weak signal"],
  ["owners", "For owners"],
] as const;

/** A screenshot, resized for the screen and linked to its full size. Tall full-page ones
 * scroll inside a frame. */
function Shot({
  name,
  alt,
  caption,
  narrow,
}: {
  name: ShotName;
  alt: string;
  caption?: string;
  narrow?: boolean;
}) {
  const { width, height } = shots[name];
  const tall = height > width * 1.2 && !narrow;
  const image = (
    <Image
      src={`/walkthrough/${name}.png`}
      alt={alt}
      width={width}
      height={height}
      sizes={narrow ? "(min-width: 640px) 320px, 80vw" : "(min-width: 1024px) 896px, 100vw"}
      className="h-auto w-full"
    />
  );
  return (
    <figure className={narrow ? "grid max-w-xs gap-2" : "grid gap-2"}>
      <div
        className={`overflow-hidden rounded-xl border border-border bg-card shadow-sm ${
          tall ? "max-h-[36rem] overflow-y-auto" : ""
        }`}
      >
        {/* Opens full size, for reading the details on a phone. */}
        <a href={`/walkthrough/${name}.png`} target="_blank" rel="noopener">
          {image}
        </a>
      </div>
      {caption ? (
        <figcaption className="text-sm text-muted-foreground">{caption}</figcaption>
      ) : null}
    </figure>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="grid scroll-mt-4 gap-5">
      <h2 id={`${id}-heading`} className="text-2xl font-semibold tracking-tight">
        {title}
      </h2>
      {children}
    </section>
  );
}

function P({ children }: { children: ReactNode }) {
  return <p className="max-w-prose">{children}</p>;
}

export default function HelpPage() {
  return (
    <>
      <SiteHeader>
        <Link href="/account">Account</Link>
      </SiteHeader>
      <main className="contours">
        <div className="mx-auto grid max-w-4xl gap-12 px-4 py-10">
          <div className="grid gap-3">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">How Cornerpin works</h1>
            <P>
              Cornerpin shows the lots in a subdivision: which are available, what they cost, where
              they are, with photos and documents. You can ask the owner about a lot, save the ones
              you like and hear when they change. This tour uses Juniper Bench, a demo subdivision.
            </P>
            <nav aria-label="On this page">
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {SECTIONS.map(([id, title]) => (
                  <li key={id}>
                    <a href={`#${id}`} className="underline">
                      {title}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>

          <Section id="finding" title="Finding a lot">
            <P>
              Each subdivision has its own page, usually reached from a sign on site or a shared
              link. The map colours every lot by status: green is available, orange is on hold,
              grey is sold. Tap a lot to open it.
            </P>
            <Shot
              name="02-subdivision"
              alt="A subdivision page with its map of lots coloured by status"
            />
            <P>
              Under the map, every lot is listed. Narrow the list by status, land only or lot with
              a home, price and size; a filtered list has its own address, so you can share it.
            </P>
            <Shot name="04-filters" alt="The lot list filtered to available lots with homes" />
            <P>
              A lot&apos;s page has the price, status, size and home details, then photos, a map
              with directions, and documents such as the plat or covenants.
            </P>
            <Shot name="05-lot" alt="A lot page with its price, status and details" />
            <div className="flex flex-wrap gap-6">
              <Shot
                name="10-mobile-subdivision"
                alt="The subdivision page on a phone"
                narrow
                caption="On a phone"
              />
              <Shot
                name="11-mobile-lot"
                alt="A lot page on a phone"
                narrow
                caption="A lot on a phone"
              />
            </div>
            <P>Sharing a lot&apos;s link by text or social media shows a preview card like this:</P>
            <Shot
              name="08-link-preview"
              alt="A link preview card for lot 2-6: available, $489,000, 0.174 acres"
            />
          </Section>

          <Section id="asking" title="Asking the owner">
            <P>
              Every lot page ends with a form to contact the owner. Anyone can ask a question; the
              owner replies by email.
            </P>
            <Shot
              name="07-contact-signed-out"
              alt="The contact form: name, email, phone and question"
            />
            <P>
              Signed in, you can also ask the owner to hold an available lot, and choose whether
              the owner may email or text you about their lots beyond replying. You can change that
              any time on your account page. No payment is taken online; the owner approves or
              declines a hold.
            </P>
            <Shot
              name="16-contact-signed-in"
              alt="The contact form when signed in, with contact permission choices"
            />
            <Shot name="17-hold-request" alt="Asking the owner to hold a lot" />
          </Section>

          <Section id="account" title="Your account">
            <P>
              There&apos;s no password. Enter your email, and we send you a link that signs you
              in; it works once, for 15 minutes. A new address gets a new account, so signing in
              is also signing up.
            </P>
            <div className="grid gap-6 sm:grid-cols-2">
              <Shot
                name="12-sign-in"
                alt="The sign-in page asking for an email address"
                caption="Enter your email"
              />
              <Shot
                name="15-verify"
                alt="The page the emailed link opens, with a Sign in button"
                caption="Open the link and sign in"
              />
            </div>
            <P>
              Save the lots you&apos;re interested in, and we&apos;ll email you when their price or
              status changes. Your account page lists them, along with who may contact you and
              your details.
            </P>
            <Shot
              name="18-account"
              alt="The account page with saved lots, alerts and contact permissions"
            />
          </Section>

          <Section id="signs" title="Signs on the lots">
            <P>
              Lots for sale can have a sign with a QR code. Scan it with your phone&apos;s camera
              to open the lot&apos;s page, with today&apos;s price and status.
            </P>
            <Shot
              name="28-printed-sign"
              alt="A printed lot sign with the lot number and a QR code"
              narrow
            />
            <P>If a lot isn&apos;t listed at the moment, the code says so.</P>
          </Section>

          <Section id="offline" title="With a weak signal">
            <P>
              Pages you&apos;ve opened stay on your phone. Open a lot once and that lot, and the
              whole subdivision&apos;s list and map, still open with no signal. A question you send
              offline is kept and sent when you&apos;re back online.
            </P>
            <Shot name="19-offline" alt="The offline page listing the pages saved on this device" />
            <P>
              To keep a subdivision on your home screen: on an iPhone, tap Share, then Add to Home
              Screen; on Android, open the browser menu and choose Install app or Add to Home
              screen.
            </P>
          </Section>

          <Section id="owners" title="For owners">
            <P>
              Owners and their staff run their subdivisions from the owner portal. Owner accounts
              are set up for you; sign in with the email address you were given.
            </P>
            <Shot
              name="22-portal-subdivision"
              alt="A subdivision in the owner portal: lots, phases and details"
            />
            <P>
              Add lots, set prices and status, and publish them when they&apos;re ready. Every price
              and status change is kept with who made it and when. Upload photos and documents, and
              print a sign for any lot.
            </P>
            <Shot
              name="24-portal-lot"
              alt="A lot in the owner portal: photos, documents, history and details"
            />
            <P>
              Draw each lot&apos;s shape on the map, or lay a scan of the plat over it and trace the
              lots. Acreage follows the shape.
            </P>
            <Shot name="25-portal-map-editor" alt="The map editor with the subdivision's lots" />
            <P>
              Questions and hold requests arrive by email and wait in Inquiries and holds.
              Approving a hold puts the lot on hold, and everyone who saved it hears about it.
            </P>
            <Shot
              name="26-portal-inquiries"
              alt="Inquiries and holds, with a pending hold request and two questions"
            />
          </Section>

          <p className="text-muted-foreground">
            Ready to look around?{" "}
            <Link href="/juniper-bench" className="underline">
              Open the demo subdivision
            </Link>
            .
          </p>
        </div>
      </main>
    </>
  );
}
