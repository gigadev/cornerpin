"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { slugify } from "@/lib/slug";
import { Field, FormMessage } from "./field";
import { TimeZoneSelect } from "./time-zone-select";

type Subdivision = components["schemas"]["SubdivisionDetail"];

/** Create (no `subdivision`) or edit a subdivision. Location is typed in until the map editor
 * arrives in P1-06. */
export function SubdivisionForm({
  tenantId,
  subdivision,
}: {
  tenantId: string;
  subdivision?: Subdivision;
}) {
  const router = useRouter();
  const [name, setName] = useState(subdivision?.name ?? "");
  const [slug, setSlug] = useState(subdivision?.slug ?? "");
  const [slugEdited, setSlugEdited] = useState(Boolean(subdivision));
  const [timeZone, setTimeZone] = useState(subdivision?.time_zone ?? "America/Boise");
  const [latitude, setLatitude] = useState(subdivision ? String(subdivision.latitude) : "");
  const [longitude, setLongitude] = useState(subdivision ? String(subdivision.longitude) : "");
  const [description, setDescription] = useState(subdivision?.description ?? "");
  const [published, setPublished] = useState(subdivision?.published ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function onNameChange(value: string) {
    setName(value);
    if (!slugEdited) setSlug(slugify(value));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(null);
    const lat = Number(latitude);
    const lng = Number(longitude);
    if (latitude.trim() === "" || longitude.trim() === "" || Number.isNaN(lat + lng)) {
      setError("Enter the latitude and longitude as numbers, e.g. 43.4005 and -116.3880.");
      return;
    }
    const body = {
      name,
      slug,
      time_zone: timeZone,
      latitude: lat,
      longitude: lng,
      description,
      published,
    };
    setBusy(true);
    if (subdivision) {
      const { error: failure } = await browserApi.PATCH(
        "/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}",
        { params: { path: { tenant_id: tenantId, subdivision_id: subdivision.id } }, body },
      );
      setBusy(false);
      if (failure) {
        setError(errorMessage(failure));
        return;
      }
      setSaved("Saved.");
      router.refresh();
    } else {
      const { data, error: failure } = await browserApi.POST(
        "/v1/tenants/{tenant_id}/subdivisions",
        { params: { path: { tenant_id: tenantId } }, body },
      );
      setBusy(false);
      if (!data) {
        setError(errorMessage(failure));
        return;
      }
      router.push(`/app/${tenantId}/subdivisions/${data.id}`);
      router.refresh();
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <Field id="subdivision-name" label="Name">
          <Input
            id="subdivision-name"
            required
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
          />
        </Field>
        <Field
          id="subdivision-slug"
          label="Web address"
          hint={`cornerpin.app/${slug || "your-subdivision"}`}
        >
          <Input
            id="subdivision-slug"
            required
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
              setSlugEdited(true);
            }}
          />
        </Field>
        <Field id="subdivision-latitude" label="Latitude" hint="Right-click the spot in a map app to copy it.">
          <Input
            id="subdivision-latitude"
            inputMode="decimal"
            required
            value={latitude}
            onChange={(event) => setLatitude(event.target.value)}
          />
        </Field>
        <Field id="subdivision-longitude" label="Longitude" hint="West is negative, e.g. -116.388.">
          <Input
            id="subdivision-longitude"
            inputMode="decimal"
            required
            value={longitude}
            onChange={(event) => setLongitude(event.target.value)}
          />
        </Field>
        <Field id="subdivision-time-zone" label="Time zone">
          <TimeZoneSelect id="subdivision-time-zone" value={timeZone} onChange={setTimeZone} />
        </Field>
      </div>
      <Field id="subdivision-description" label="Description">
        <Textarea
          id="subdivision-description"
          rows={4}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </Field>
      <div className="flex items-center gap-2">
        <Checkbox
          id="subdivision-published"
          checked={published}
          onCheckedChange={(checked) => setPublished(checked === true)}
        />
        <Label htmlFor="subdivision-published">Published (visible to the public)</Label>
      </div>
      <FormMessage error={error} success={saved} />
      <div>
        <Button type="submit" disabled={busy}>
          {subdivision ? "Save subdivision" : "Create subdivision"}
        </Button>
      </div>
    </form>
  );
}
