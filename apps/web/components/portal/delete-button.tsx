"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";

type Removal = Promise<{ error?: unknown; response: Response }>;

/** Asks first, then runs `remove`; on success goes to `then`. Shows the API's reason on 409. */
function DeleteButton({
  label,
  confirmText,
  remove,
  then,
}: {
  label: string;
  confirmText: string;
  remove: () => Removal;
  then: string;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onClick() {
    if (!window.confirm(confirmText)) return;
    setBusy(true);
    const { error: failure, response } = await remove();
    setBusy(false);
    if (response.ok) {
      router.push(then);
      router.refresh();
    } else {
      setError(errorMessage(failure));
    }
  }

  return (
    <div className="grid gap-2">
      <div>
        <Button type="button" variant="destructive" onClick={onClick} disabled={busy}>
          {label}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function DeleteSubdivisionButton({
  tenantId,
  subdivisionId,
  name,
}: {
  tenantId: string;
  subdivisionId: string;
  name: string;
}) {
  return (
    <DeleteButton
      label="Delete subdivision"
      confirmText={`Delete ${name}? This can't be undone.`}
      then={`/app/${tenantId}`}
      remove={() =>
        browserApi.DELETE("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}", {
          params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
        })
      }
    />
  );
}

export function DeleteLotButton({
  tenantId,
  lotId,
  subdivisionId,
  number,
}: {
  tenantId: string;
  lotId: string;
  subdivisionId: string;
  number: string;
}) {
  return (
    <DeleteButton
      label="Delete lot"
      confirmText={`Delete lot ${number}? This can't be undone.`}
      then={`/app/${tenantId}/subdivisions/${subdivisionId}`}
      remove={() =>
        browserApi.DELETE("/v1/tenants/{tenant_id}/lots/{lot_id}", {
          params: { path: { tenant_id: tenantId, lot_id: lotId } },
        })
      }
    />
  );
}
