"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
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
import { formatAcres } from "@/lib/format";
import { FormMessage } from "./field";

type FeatureCollection = components["schemas"]["FeatureCollection"];
type ImportReport = components["schemas"]["ImportReport"];

const NO_PHASE = "none";
const ACTION_LABELS = { update: "Update", create: "Create", skip: "Skip" } as const;

function asFeatureCollection(text: string): FeatureCollection | null {
  try {
    const parsed: unknown = JSON.parse(text);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      "type" in parsed &&
      parsed.type === "FeatureCollection"
    ) {
      // The API validates the rest and explains anything it can't use.
      return parsed as FeatureCollection;
    }
  } catch {
    // Not JSON at all; handled below.
  }
  return null;
}

/** Import lot shapes from a GeoJSON file: preview what matches, then apply (ADR-026). */
export function GeoJsonImport({
  tenantId,
  subdivisionId,
  phases,
}: {
  tenantId: string;
  subdivisionId: string;
  phases: { id: string; name: string }[];
}) {
  const router = useRouter();
  const [collection, setCollection] = useState<FeatureCollection | null>(null);
  const [phaseId, setPhaseId] = useState<string>(NO_PHASE);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(next: FeatureCollection, apply: boolean, phase: string) {
    setBusy(true);
    const { data, error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/import",
      {
        params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
        body: { collection: next, apply, phase_id: phase === NO_PHASE ? null : phase },
      },
    );
    setBusy(false);
    if (!data) {
      setError(errorMessage(failure));
      setReport(null);
      return;
    }
    setError(null);
    setReport(data);
    if (apply) router.refresh();
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const parsed = asFeatureCollection(await file.text());
    if (!parsed) {
      setError("That isn't a GeoJSON FeatureCollection.");
      setCollection(null);
      setReport(null);
      return;
    }
    setCollection(parsed);
    await run(parsed, false, phaseId);
  }

  async function onPhase(value: string) {
    setPhaseId(value);
    if (collection) await run(collection, false, value);
  }

  const usable = report?.rows.filter((row) => row.action !== "skip").length ?? 0;

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted-foreground">
        A GeoJSON file of lot polygons in longitude/latitude (WGS 84). Each shape is matched to a
        lot by a property such as <code>number</code>, <code>lot</code> or <code>name</code>.
        Nothing is saved until you apply it.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="geojson-file">GeoJSON file</Label>
          <input
            id="geojson-file"
            type="file"
            accept=".geojson,.json,application/geo+json,application/json"
            onChange={onFile}
            className="text-sm"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="geojson-phase">Lots not here yet</Label>
          <Select value={phaseId} onValueChange={onPhase}>
            <SelectTrigger id="geojson-phase" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_PHASE}>Skip them</SelectItem>
              {phases.map((phase) => (
                <SelectItem key={phase.id} value={phase.id}>
                  Create them in {phase.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {report ? (
        <div className="grid gap-3">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1 font-medium">Feature</th>
                <th className="py-1 font-medium">Lot</th>
                <th className="py-1 font-medium">Action</th>
                <th className="py-1 font-medium">Details</th>
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row) => (
                <tr key={row.index} className="border-t border-border">
                  <td className="py-1 tabular-nums">{row.index + 1}</td>
                  <td className="py-1">{row.number ?? "—"}</td>
                  <td className="py-1">{ACTION_LABELS[row.action]}</td>
                  <td className="py-1 text-muted-foreground">
                    {row.reason ?? formatAcres(row.acreage)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {report.lots_without_shape.length > 0 ? (
            <p className="text-sm text-muted-foreground">
              Not in the file: lot {report.lots_without_shape.join(", ")}.
            </p>
          ) : null}
          {report.applied ? (
            <p role="status" className="text-sm">
              Imported {usable} {usable === 1 ? "shape" : "shapes"}.
            </p>
          ) : (
            <div>
              <Button
                type="button"
                onClick={() => collection && run(collection, true, phaseId)}
                disabled={busy || usable === 0}
              >
                Apply import ({usable})
              </Button>
            </div>
          )}
        </div>
      ) : null}
      <FormMessage error={error} />
    </div>
  );
}
