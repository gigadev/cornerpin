"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Field, FormMessage } from "@/components/portal/field";
import { TimeZoneSelect } from "@/components/portal/time-zone-select";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { channelLabel, formatWhen } from "@/lib/format";

// The buyer's account page (P1-08): their details, alerts and who may contact them.

type Me = components["schemas"]["Me"];
type Prefs = components["schemas"]["NotificationPrefs"];
type Consent = components["schemas"]["ConsentOut"];

export function ProfileForm({ me }: { me: Me }) {
  const router = useRouter();
  const [name, setName] = useState(me.display_name ?? "");
  const [phone, setPhone] = useState(me.phone ?? "");
  const [timeZone, setTimeZone] = useState(me.time_zone ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { data, error: failure } = await browserApi.PATCH("/v1/me", {
      body: { display_name: name, phone: phone.trim() || null, time_zone: timeZone || null },
    });
    if (failure || !data) {
      setSaved(null);
      setError(errorMessage(failure));
      return;
    }
    setError(null);
    setPhone(data.phone ?? "");
    setSaved("Saved");
    router.refresh();
  }

  return (
    <form onSubmit={save} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="profile-name" label="Name">
          <Input
            id="profile-name"
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        <Field id="profile-phone" label="Phone" hint="US numbers as you'd dial them; others with +">
          <Input
            id="profile-phone"
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
          />
        </Field>
        <Field id="profile-time-zone" label="Time zone">
          <TimeZoneSelect id="profile-time-zone" value={timeZone} onChange={setTimeZone} />
        </Field>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" variant="outline">
          Save details
        </Button>
        <FormMessage error={error} success={saved} />
      </div>
    </form>
  );
}

export function AlertsForm({ prefs }: { prefs: Prefs }) {
  const [email, setEmail] = useState(prefs.email_saved_lot_changes);
  const [error, setError] = useState<string | null>(null);

  async function change(next: boolean) {
    setEmail(next);
    const { error: failure } = await browserApi.PUT("/v1/me/notification-prefs", {
      body: { ...prefs, email_saved_lot_changes: next },
    });
    if (failure) {
      setEmail(!next);
      setError(errorMessage(failure));
    } else {
      setError(null);
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex items-center gap-2">
        <Checkbox
          id="alert-email"
          checked={email}
          onCheckedChange={(checked) => void change(checked === true)}
        />
        <Label htmlFor="alert-email" className="font-normal">
          Email me when a saved lot&apos;s status or price changes
        </Label>
      </div>
      <FormMessage error={error} />
    </div>
  );
}

export function SavedLotRemove({ lotId, number }: { lotId: string; number: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    await browserApi.DELETE("/v1/me/saved-lots/{lot_id}", {
      params: { path: { lot_id: lotId } },
    });
    router.refresh();
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      disabled={busy}
      onClick={remove}
      aria-label={`Remove lot ${number}`}
    >
      Remove
    </Button>
  );
}

export function ConsentList({ consents, timeZone }: { consents: Consent[]; timeZone: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function change(consent: Consent, granted: boolean) {
    const { error: failure } = await browserApi.POST("/v1/me/consents", {
      body: { tenant_id: consent.tenant_id, channel: consent.channel, granted },
    });
    setError(failure ? errorMessage(failure) : null);
    router.refresh();
  }

  return (
    <div className="grid gap-2">
      <ul className="divide-y divide-border rounded-lg border border-border">
        {consents.map((consent) => {
          const id = `consent-${consent.tenant_id}-${consent.channel}`;
          return (
            <li key={id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
              <div className="flex items-center gap-2">
                <Checkbox
                  id={id}
                  checked={consent.granted}
                  onCheckedChange={(checked) => void change(consent, checked === true)}
                />
                <Label htmlFor={id} className="font-normal">
                  {channelLabel(consent.channel)} from {consent.tenant_name}
                </Label>
              </div>
              <span className="text-sm text-muted-foreground sm:ml-auto">
                {consent.granted ? "Allowed" : "Not allowed"} since{" "}
                {formatWhen(consent.recorded_at, timeZone)}
              </span>
            </li>
          );
        })}
      </ul>
      <FormMessage error={error} />
    </div>
  );
}
