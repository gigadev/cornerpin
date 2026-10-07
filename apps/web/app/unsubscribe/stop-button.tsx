"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";

export function StopButton({
  token,
  tenantName,
  channel,
  allowed,
}: {
  token: string;
  tenantName: string;
  channel: string;
  allowed: boolean;
}) {
  const [stopped, setStopped] = useState(!allowed);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function stop() {
    setBusy(true);
    const { data, error: failure } = await browserApi.POST("/v1/unsubscribe", {
      params: { query: { token } },
    });
    setBusy(false);
    if (failure || !data) setError(errorMessage(failure));
    else setStopped(!data.allowed);
  }

  if (stopped) {
    return (
      <p role="status">
        Done. {tenantName} won&apos;t send you {channel} about their lots. You can change this
        on{" "}
        <Link href="/account" className="underline">
          your account page
        </Link>
        .
      </p>
    );
  }
  return (
    <div className="grid gap-4">
      <p>
        Stop {tenantName} sending you {channel} about their lots? Replies to your own questions
        still reach you.
      </p>
      <Button onClick={stop} disabled={busy} className="h-10">
        Stop {channel} from {tenantName}
      </Button>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
