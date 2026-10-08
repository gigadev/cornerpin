"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { FormMessage } from "./field";

/** Approve (which puts an available lot on hold) or decline a pending hold request. */
export function HoldDecision({
  tenantId,
  holdId,
  who,
  scoreId,
}: {
  tenantId: string;
  holdId: string;
  who: string;
  /** The score shown beside the hold, logged with the decision (ADR-047). */
  scoreId: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide(decision: "approve" | "decline") {
    setBusy(true);
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/hold-requests/{hold_id}/decision",
      { params: { path: { tenant_id: tenantId, hold_id: holdId } }, body: { decision, score_id: scoreId } },
    );
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return (
    <div className="grid gap-1">
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => decide("approve")}
          aria-label={`Approve hold for ${who}`}
        >
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => decide("decline")}
          aria-label={`Decline hold for ${who}`}
        >
          Decline
        </Button>
      </div>
      <FormMessage error={error} />
    </div>
  );
}
