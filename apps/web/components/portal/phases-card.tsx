"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { RELEASE_STATUSES, releaseLabel, type ReleaseStatus } from "@/lib/format";
import { Field, FormMessage } from "./field";

type Phase = components["schemas"]["PhaseOut"];

function isReleaseStatus(value: string): value is ReleaseStatus {
  return (RELEASE_STATUSES as readonly string[]).includes(value);
}

function PhaseRow({ tenantId, phase }: { tenantId: string; phase: Phase }) {
  const router = useRouter();
  const [name, setName] = useState(phase.name);
  const [release, setRelease] = useState<ReleaseStatus>(phase.release_status);
  const [error, setError] = useState<string | null>(null);
  const dirty = name !== phase.name || release !== phase.release_status;
  const path = { tenant_id: tenantId, phase_id: phase.id };

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { error: failure } = await browserApi.PATCH("/v1/tenants/{tenant_id}/phases/{phase_id}", {
      params: { path },
      body: { name, release_status: release },
    });
    if (failure) setError(errorMessage(failure));
    else {
      setError(null);
      router.refresh();
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${phase.name}?`)) return;
    const { error: failure } = await browserApi.DELETE(
      "/v1/tenants/{tenant_id}/phases/{phase_id}",
      { params: { path } },
    );
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  return (
    <li className="grid gap-2 py-3">
      <form onSubmit={save} className="flex flex-wrap items-end gap-2">
        <Input
          aria-label={`Name of ${phase.name}`}
          className="w-44"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Select
          value={release}
          onValueChange={(value) => {
            if (isReleaseStatus(value)) setRelease(value);
          }}
        >
          <SelectTrigger aria-label={`Release status of ${phase.name}`} className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RELEASE_STATUSES.map((status) => (
              <SelectItem key={status} value={status}>
                {releaseLabel(status)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">
          {phase.lot_count} {phase.lot_count === 1 ? "lot" : "lots"}
        </span>
        <div className="ml-auto flex gap-2">
          <Button type="submit" variant="outline" size="sm" disabled={!dirty}>
            Save
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={remove}>
            Delete
          </Button>
        </div>
      </form>
      <FormMessage error={error} />
    </li>
  );
}

export function PhasesCard({
  tenantId,
  subdivisionId,
  phases,
}: {
  tenantId: string;
  subdivisionId: string;
  phases: Phase[];
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/phases",
      {
        params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
        body: { name, sort_order: phases.length },
      },
    );
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    setName("");
    setError(null);
    router.refresh();
  }

  return (
    <div className="grid gap-4">
      {phases.length === 0 ? (
        <p className="text-sm text-muted-foreground">No phases yet. Lots belong to a phase.</p>
      ) : (
        <ul className="divide-y divide-border">
          {phases.map((phase) => (
            <PhaseRow key={phase.id} tenantId={tenantId} phase={phase} />
          ))}
        </ul>
      )}
      <form onSubmit={add} className="flex flex-wrap items-end gap-2">
        <Field id="new-phase-name" label="New phase">
          <Input
            id="new-phase-name"
            className="w-56"
            required
            placeholder={`Phase ${phases.length + 1}`}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Button type="submit" variant="outline">
          Add phase
        </Button>
      </form>
      <FormMessage error={error} />
    </div>
  );
}
