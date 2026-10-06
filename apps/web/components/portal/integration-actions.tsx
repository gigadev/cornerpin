"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { toggleLabel, type Provider } from "@/lib/integrations";
import { Field, FormMessage } from "./field";

// What an owner does with a connection (P2-07, P2-08): switch it on or off, remove it, and for
// Salesforce, give the credentials of the app they made in their org. Adding Slack is a plain
// link to the API, which sends the owner to Slack and back.

function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<{ error?: unknown }>) {
    setBusy(true);
    setError(null);
    const { error: failure } = await action();
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return { busy, error, run };
}

export function IntegrationActions({
  tenantId,
  provider,
  enabled,
  canToggle,
}: {
  tenantId: string;
  provider: Provider;
  enabled: boolean;
  canToggle: boolean;
}) {
  const { busy, error, run } = useAction();
  const path = { params: { path: { tenant_id: tenantId, provider } } };

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap gap-2">
        {canToggle ? (
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              run(() =>
                browserApi.PATCH("/v1/tenants/{tenant_id}/integrations/{provider}", {
                  ...path,
                  body: { enabled: !enabled },
                }),
              )
            }
          >
            {toggleLabel(provider, enabled)}
          </Button>
        ) : null}
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            run(() => browserApi.DELETE("/v1/tenants/{tenant_id}/integrations/{provider}", path))
          }
        >
          Disconnect
        </Button>
      </div>
      <FormMessage error={error} />
    </div>
  );
}

export function SalesforceForm({ tenantId }: { tenantId: string }) {
  const { busy, error, run } = useAction();
  const [domain, setDomain] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(() =>
      browserApi.POST("/v1/tenants/{tenant_id}/integrations/salesforce", {
        params: { path: { tenant_id: tenantId } },
        body: { domain, client_id: clientId, client_secret: clientSecret },
      }),
    );
  }

  // The secret is an app's API credential, typed once and never shown again: a plain field
  // that browsers won't offer to save.
  const secretProps = { autoComplete: "off", spellCheck: false, autoCapitalize: "off" } as const;

  return (
    <form onSubmit={submit} className="grid max-w-xl gap-3" aria-label="Connect Salesforce">
      <Field
        id="sf-domain"
        label="My Domain"
        hint="From Setup → My Domain, like yourcompany.my.salesforce.com"
      >
        <Input
          id="sf-domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          required
          {...secretProps}
        />
      </Field>
      <Field id="sf-key" label="Consumer key" hint="From your External Client App">
        <Input
          id="sf-key"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          required
          {...secretProps}
        />
      </Field>
      <Field id="sf-secret" label="Consumer secret" hint="Stored encrypted; nobody can read it back">
        <Input
          id="sf-secret"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          required
          {...secretProps}
        />
      </Field>
      <div>
        <Button type="submit" disabled={busy}>
          Connect Salesforce
        </Button>
      </div>
      <FormMessage error={error} />
    </form>
  );
}
