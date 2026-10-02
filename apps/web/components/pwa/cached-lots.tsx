"use client";

import { useEffect, useState } from "react";
import { CACHES } from "@/lib/pwa-caches";
import { isPublicPage, publicPage } from "@/lib/pwa-paths";

type Kept = { path: string; title: string; lot: boolean };

/** "Lot 7, Juniper Bench · Cornerpin" -> "Lot 7, Juniper Bench". */
function pageTitle(html: string, fallback: string): string {
  const title = /<title>([^<]*)<\/title>/.exec(html)?.[1];
  return title ? title.replace(/ · Cornerpin$/, "").replace(/&amp;/g, "&") : fallback;
}

async function keptPages(): Promise<Kept[]> {
  if (!("caches" in window)) return [];
  const cache = await caches.open(CACHES.pages);
  const kept: Kept[] = [];
  for (const request of await cache.keys()) {
    const url = new URL(request.url);
    if (url.search || !isPublicPage(url.pathname)) continue;
    const response = await cache.match(request);
    const html = response ? await response.text() : "";
    kept.push({
      path: url.pathname,
      title: pageTitle(html, url.pathname),
      lot: publicPage(url.pathname)?.lot != null,
    });
  }
  // Subdivisions first, then lots, in number order.
  return kept.sort(
    (a, b) =>
      Number(a.lot) - Number(b.lot) || a.title.localeCompare(b.title, "en", { numeric: true }),
  );
}

/** The public pages this device has kept, so a buyer offline can still open them. */
export function CachedLots() {
  const [pages, setPages] = useState<Kept[] | null>(null);

  useEffect(() => {
    void keptPages().then(setPages);
  }, []);

  if (pages === null) return null;
  if (pages.length === 0) {
    return <p className="text-muted-foreground">Nothing is saved on this device yet.</p>;
  }
  return (
    <ul className="divide-y divide-border rounded-lg border border-border">
      {pages.map((page) => (
        <li key={page.path}>
          {/* A full page load, so the service worker answers from its cache. */}
          <a href={page.path} className="block px-4 py-3 underline-offset-4 hover:underline">
            {page.title}
          </a>
        </li>
      ))}
    </ul>
  );
}
