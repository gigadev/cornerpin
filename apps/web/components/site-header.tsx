import Link from "next/link";
import type { ReactNode } from "react";
import { Wordmark } from "@/components/wordmark";

// Links passed in as children pick up the header's link style.
export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="border-b border-border bg-card/80 backdrop-blur print:hidden">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" aria-label="Cornerpin home" className="rounded-md">
          <Wordmark />
        </Link>
        <nav
          aria-label="Site"
          className="flex items-center gap-3 text-sm font-medium sm:gap-4 [&_a]:text-foreground/80 [&_a]:underline-offset-4 [&_a:hover]:text-foreground [&_a:hover]:underline [&_button]:text-foreground/80 [&_button:hover]:text-foreground [&_button:hover]:underline"
        >
          <Link href="/help">Help</Link>
          {children}
        </nav>
      </div>
    </header>
  );
}
