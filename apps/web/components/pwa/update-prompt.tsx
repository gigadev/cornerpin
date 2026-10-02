"use client";

import { useSerwist } from "@serwist/turbopack/react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

// A new version of the app waits instead of replacing the running one mid-task (ADR-030).
export function UpdatePrompt() {
  const { serwist } = useSerwist();
  const [waiting, setWaiting] = useState(false);

  useEffect(() => {
    if (!serwist) return;
    const onWaiting = () => setWaiting(true);
    serwist.addEventListener("waiting", onWaiting);
    void navigator.serviceWorker.getRegistration().then((registration) => {
      if (registration?.waiting && navigator.serviceWorker.controller) setWaiting(true);
    });
    return () => serwist.removeEventListener("waiting", onWaiting);
  }, [serwist]);

  if (!waiting || !serwist) return null;

  function reload() {
    serwist?.addEventListener("controlling", () => window.location.reload());
    serwist?.messageSkipWaiting();
  }

  return (
    <div
      role="status"
      className="flex items-center gap-3 rounded-lg border border-border bg-card p-3 shadow-lg"
    >
      <p className="text-sm">A new version of Cornerpin is ready.</p>
      <Button size="sm" className="ml-auto" onClick={reload}>
        Reload
      </Button>
      <Button size="sm" variant="ghost" onClick={() => setWaiting(false)}>
        Later
      </Button>
    </div>
  );
}
