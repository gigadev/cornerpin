import Link from "next/link";
import type { ReactNode } from "react";

export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Cornerpin
        </Link>
        {children ? <div className="flex items-center gap-3 text-sm">{children}</div> : null}
      </div>
    </header>
  );
}
