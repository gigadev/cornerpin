"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import type { components } from "@/lib/api/schema";
import {
  LISTING_TYPES,
  LOT_STATUSES,
  listingLabel,
  parseDollars,
  parseOptionalNumber,
  statusLabel,
  type ListingType,
  type LotStatus,
} from "@/lib/format";
import { Field, FormMessage } from "./field";

type Lot = components["schemas"]["LotDetail"];
type PhaseOption = { id: string; name: string };

function oneOf<T extends string>(options: readonly T[], value: string): value is T {
  return (options as readonly string[]).includes(value);
}

function text(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Create (no `lot`) or edit a lot. Saving a new status or price adds to its history. */
export function LotForm({
  tenantId,
  subdivisionId,
  phases,
  lot,
}: {
  tenantId: string;
  subdivisionId: string;
  phases: PhaseOption[];
  lot?: Lot;
}) {
  const router = useRouter();
  const [number, setNumber] = useState(lot?.number ?? "");
  const [phaseId, setPhaseId] = useState(lot?.phase_id ?? phases[0]?.id ?? "");
  const [status, setStatus] = useState<LotStatus>(lot?.status ?? "available");
  const [listingType, setListingType] = useState<ListingType>(lot?.listing_type ?? "land_only");
  const [price, setPrice] = useState(text(lot?.price));
  const [acreage, setAcreage] = useState(text(lot?.acreage));
  const [published, setPublished] = useState(lot?.published ?? false);
  const [bedrooms, setBedrooms] = useState(text(lot?.home?.bedrooms));
  const [bathrooms, setBathrooms] = useState(text(lot?.home?.bathrooms));
  const [squareFeet, setSquareFeet] = useState(text(lot?.home?.square_feet));
  const [homeDescription, setHomeDescription] = useState(lot?.home?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    const dollars = parseDollars(price);
    if (Number.isNaN(dollars)) {
      setError("Enter the price in whole dollars, e.g. 95000.");
      return;
    }
    const acres = parseOptionalNumber(acreage);
    if (acres !== null && !(acres > 0)) {
      setError("Acreage must be a positive number.");
      return;
    }
    const home =
      listingType === "lot_and_home"
        ? {
            bedrooms: parseOptionalNumber(bedrooms),
            bathrooms: parseOptionalNumber(bathrooms),
            square_feet: parseOptionalNumber(squareFeet),
            description: homeDescription.trim() || null,
          }
        : null;
    const body = {
      number,
      phase_id: phaseId,
      status,
      listing_type: listingType,
      price: dollars,
      acreage: acres,
      published,
      home,
    };

    setBusy(true);
    if (lot) {
      const { error: failure } = await browserApi.PATCH("/v1/tenants/{tenant_id}/lots/{lot_id}", {
        params: { path: { tenant_id: tenantId, lot_id: lot.id } },
        body,
      });
      setBusy(false);
      if (failure) {
        setError(errorMessage(failure));
        return;
      }
      setSaved("Saved.");
      router.refresh();
    } else {
      const { data, error: failure } = await browserApi.POST(
        "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/lots",
        { params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } }, body },
      );
      setBusy(false);
      if (!data) {
        setError(errorMessage(failure));
        return;
      }
      router.push(`/app/${tenantId}/lots/${data.id}`);
      router.refresh();
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id="lot-number" label="Lot number">
          <Input
            id="lot-number"
            required
            value={number}
            onChange={(event) => setNumber(event.target.value)}
          />
        </Field>
        <Field id="lot-phase" label="Phase">
          <Select value={phaseId} onValueChange={setPhaseId}>
            <SelectTrigger id="lot-phase" className="w-full">
              <SelectValue placeholder="Choose a phase" />
            </SelectTrigger>
            <SelectContent>
              {phases.map((phase) => (
                <SelectItem key={phase.id} value={phase.id}>
                  {phase.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id="lot-status" label="Status">
          <Select
            value={status}
            onValueChange={(value) => {
              if (oneOf(LOT_STATUSES, value)) setStatus(value);
            }}
          >
            <SelectTrigger id="lot-status" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOT_STATUSES.map((option) => (
                <SelectItem key={option} value={option}>
                  {statusLabel(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id="lot-listing-type" label="Listing">
          <Select
            value={listingType}
            onValueChange={(value) => {
              if (oneOf(LISTING_TYPES, value)) setListingType(value);
            }}
          >
            <SelectTrigger id="lot-listing-type" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LISTING_TYPES.map((option) => (
                <SelectItem key={option} value={option}>
                  {listingLabel(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id="lot-price" label="Price (whole dollars)" hint="Leave empty if not priced yet.">
          <Input
            id="lot-price"
            inputMode="numeric"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
          />
        </Field>
        <Field id="lot-acreage" label="Acreage" hint="Calculated from the boundary once it's drawn.">
          <Input
            id="lot-acreage"
            inputMode="decimal"
            value={acreage}
            onChange={(event) => setAcreage(event.target.value)}
          />
        </Field>
      </div>

      {listingType === "lot_and_home" ? (
        <fieldset className="grid gap-5 rounded-lg border border-border p-4">
          <legend className="px-1 text-sm font-medium">Home</legend>
          <div className="grid gap-5 sm:grid-cols-3">
            <Field id="home-bedrooms" label="Bedrooms">
              <Input
                id="home-bedrooms"
                inputMode="numeric"
                value={bedrooms}
                onChange={(event) => setBedrooms(event.target.value)}
              />
            </Field>
            <Field id="home-bathrooms" label="Bathrooms">
              <Input
                id="home-bathrooms"
                inputMode="decimal"
                value={bathrooms}
                onChange={(event) => setBathrooms(event.target.value)}
              />
            </Field>
            <Field id="home-square-feet" label="Square feet">
              <Input
                id="home-square-feet"
                inputMode="numeric"
                value={squareFeet}
                onChange={(event) => setSquareFeet(event.target.value)}
              />
            </Field>
          </div>
          <Field id="home-description" label="About the home">
            <Textarea
              id="home-description"
              rows={3}
              value={homeDescription}
              onChange={(event) => setHomeDescription(event.target.value)}
            />
          </Field>
        </fieldset>
      ) : null}

      <div className="flex items-center gap-2">
        <Checkbox
          id="lot-published"
          checked={published}
          onCheckedChange={(checked) => setPublished(checked === true)}
        />
        <Label htmlFor="lot-published">Published (visible to the public)</Label>
      </div>
      <FormMessage error={error} success={saved} />
      <div>
        <Button type="submit" disabled={busy || !phaseId}>
          {lot ? "Save lot" : "Create lot"}
        </Button>
      </div>
    </form>
  );
}
