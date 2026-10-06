"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { isLeadStage, LEAD_STAGES, leadStageLabel, type LeadStage } from "@/lib/leads";
import { Field, FormMessage } from "./field";

// What an owner does on a lead's page (P2-02): change its stage, add a note, mark a handoff
// handled. Each goes on the timeline, which the refresh shows.

type Path = { params: { path: { tenant_id: string; lead_id: string } } };

function path(tenantId: string, leadId: string): Path {
  return { params: { path: { tenant_id: tenantId, lead_id: leadId } } };
}

export function LeadStageSelect({
  tenantId,
  leadId,
  stage,
}: {
  tenantId: string;
  leadId: string;
  stage: LeadStage;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(value: string) {
    if (!isLeadStage(value) || value === stage) return;
    setBusy(true);
    const { error: failure } = await browserApi.PATCH(
      "/v1/tenants/{tenant_id}/leads/{lead_id}",
      { ...path(tenantId, leadId), body: { stage: value } },
    );
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return (
    <div className="grid gap-1">
      <Field id="lead-stage" label="Stage">
        <Select value={stage} onValueChange={change} disabled={busy}>
          <SelectTrigger id="lead-stage" className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEAD_STAGES.map((option) => (
              <SelectItem key={option} value={option}>
                {leadStageLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <FormMessage error={error} />
    </div>
  );
}

export function LeadNoteForm({ tenantId, leadId }: { tenantId: string; leadId: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/leads/{lead_id}/notes",
      { ...path(tenantId, leadId), body: { text } },
    );
    setBusy(false);
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    setText("");
    setError(null);
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="grid gap-2">
      <Field id="lead-note" label="Add a note" hint="Only your organization sees notes.">
        <Textarea
          id="lead-note"
          value={text}
          onChange={(event) => setText(event.target.value)}
          maxLength={2000}
          rows={3}
        />
      </Field>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy || text.trim() === ""}>
          Add note
        </Button>
        <FormMessage error={error} />
      </div>
    </form>
  );
}

export function ResolveHandoff({ tenantId, leadId }: { tenantId: string; leadId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve() {
    setBusy(true);
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/leads/{lead_id}/handoff/resolve",
      path(tenantId, leadId),
    );
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return (
    <div className="grid gap-1">
      <Button size="sm" variant="outline" disabled={busy} onClick={resolve}>
        Mark handled
      </Button>
      <FormMessage error={error} />
    </div>
  );
}
