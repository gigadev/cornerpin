import type { Metadata } from "next";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/site-header";
import { getMe } from "@/lib/api/server";
import { SignOutButton } from "./sign-out-button";

// The owner portal is online-only and never cached by the service worker (ADR-005).
export const metadata: Metadata = { title: "Owner portal · Cornerpin", robots: { index: false } };

export default async function PortalLayout({ children }: { children: ReactNode }) {
  const me = await getMe();
  if (!me) redirect("/signin?next=/app");

  return (
    <>
      <SiteHeader>
        <span className="hidden text-muted sm:inline">{me.email}</span>
        <SignOutButton />
      </SiteHeader>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </>
  );
}
