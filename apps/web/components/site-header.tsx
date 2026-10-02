import Link from "next/link";
import type { ReactNode } from "react";

export function SiteHeader({ children }: { children?: ReactNode }) {
  return (
    <header className="border-b border-border print:hidden">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Cornerpin
        </Link>
        <div className="flex items-center gap-3 text-sm">
          <Link href="/help" className="underline">
            Help
          </Link>
          {children}
        </div>
      </div>
    </header>
  );
}
