"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { isPublicPage } from "@/lib/pwa-paths";

// Keeps each public page a visitor views available offline (ADR-030). A page loaded through
// the service worker is kept by it already; pages reached by client-side navigation, and the
// very first page before the worker took over, are sent to it here. The worker decides again
// what it may keep, so nothing private is cached whatever this sends.

function keep(pathname: string): void {
  if (!isPublicPage(pathname)) return;
  navigator.serviceWorker.controller?.postMessage({
    type: "CACHE_URLS",
    payload: { urlsToCache: [pathname] },
  });
}

export function PageCacher() {
  const pathname = usePathname();
  const firstPage = useRef(true);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const worker = navigator.serviceWorker;
    if (!firstPage.current) {
      keep(pathname);
      return;
    }
    firstPage.current = false;
    if (worker.controller) return; // this page came through the worker
    const onControl = () => keep(window.location.pathname);
    worker.addEventListener("controllerchange", onControl, { once: true });
    return () => worker.removeEventListener("controllerchange", onControl);
  }, [pathname]);

  return null;
}
