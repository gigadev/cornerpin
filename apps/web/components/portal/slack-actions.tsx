"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { FormMessage } from "./field";

// Switching Slack alerts on or off, and removing the connection (P2-07). Adding Slack is a plain
// link to the API, which sends the owner to Slack and back.

export function SlackActions({ tenantId, enabled }: { tenantId: string; enabled: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { params: { path: { tenant_id: tenantId } } };

  async function run(action: () => Promise<{ error?: unknown }>) {
    setBusy(true);
    setError(null);
    const { error: failure } = await action();
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            run(() =>
              browserApi.PATCH("/v1/tenants/{tenant_id}/integrations/slack", {
                ...path,
                body: { enabled: !enabled },
              }),
            )
          }
        >
          {enabled ? "Turn alerts off" : "Turn alerts on"}
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            run(() => browserApi.DELETE("/v1/tenants/{tenant_id}/integrations/slack", path))
          }
        >
          Disconnect
        </Button>
      </div>
      <FormMessage error={error} />
    </div>
  );
}
