"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Field, FormMessage } from "@/components/portal/field";
import { Turnstile } from "@/components/turnstile";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { isNetworkFailure, queueInquiry } from "@/lib/inquiry-queue";
import { useOnline } from "@/lib/use-online";
import { useBuyerLot, type BuyerLot } from "./buyer-lot";

// Ask the owner about a lot, or ask them to hold it (P1-08, ADR-015, ADR-028). Anyone can ask
// a question. Holds and contact permission need a signed-in, so verified, email address.

type Kind = "question" | "hold";

function ContactForm({
  buyer,
  lotLabel,
  subdivisionName,
  available,
}: {
  buyer: Extract<BuyerLot, { kind: "signed-in" | "signed-out" }>;
  lotLabel: string;
  subdivisionName: string;
  available: boolean;
}) {
  const { lotId, signInHref, reload } = useBuyerLot();
  const online = useOnline();
  const signedIn = buyer.kind === "signed-in" ? buyer.state : null;
  const canHold = available && signedIn !== null && !signedIn.pending_hold;

  const [kind, setKind] = useState<Kind>("question");
  const [name, setName] = useState(signedIn?.display_name ?? "");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState(signedIn?.phone ?? "");
  const [message, setMessage] = useState("");
  const [allowEmail, setAllowEmail] = useState(signedIn?.contact.email ?? false);
  const [allowSms, setAllowSms] = useState(signedIn?.contact.sms ?? false);
  const [token, setToken] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const holding = canHold && kind === "hold";
  const contact = signedIn ? { email: allowEmail, sms: allowSms } : undefined;

  /** Offline, a question is kept on this device and sent later (ADR-030); a hold is not. */
  function keepForLater(optionalPhone: string | null) {
    const kept = queueInquiry({
      lotId,
      lotLabel,
      signedIn: signedIn !== null,
      name,
      email: signedIn ? null : email,
      phone: optionalPhone,
      message,
      contact: contact ?? null,
    });
    if (!kept) {
      setError("You're offline, and this browser won't keep your question. Try again later.");
      return;
    }
    setSent(
      "You're offline. Your question is saved on this device and will be sent when you're " +
        "back online.",
    );
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const path = { lot_id: lotId };
    const optionalPhone = phone.trim() || null;
    if (!holding && !navigator.onLine) {
      keepForLater(optionalPhone);
      return;
    }
    setSending(true);
    let failure: unknown;
    try {
      ({ error: failure } = holding
        ? await browserApi.POST("/v1/lots/{lot_id}/hold-requests", {
            params: { path },
            body: { name, phone: optionalPhone, message, contact },
          })
        : await browserApi.POST("/v1/lots/{lot_id}/inquiries", {
            params: { path },
            body: signedIn
              ? { name, phone: optionalPhone, message, contact }
              : { name, email, phone: optionalPhone, message, turnstile_token: token },
          }));
    } catch (thrown) {
      setSending(false);
      if (!isNetworkFailure(thrown)) throw thrown;
      if (holding) setError("You're offline. Ask for the hold again when you have a connection.");
      else keepForLater(optionalPhone);
      return;
    }
    setSending(false);
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    const replyTo = signedIn?.email ?? email;
    setSent(
      holding
        ? `Hold requested. The owner will reply to ${replyTo} once they decide.`
        : `Sent. The owner will reply to ${replyTo}.`,
    );
    setMessage("");
    if (signedIn) await reload();
  }

  if (sent) {
    return (
      <div className="grid gap-3">
        <p role="status" className="rounded-lg border border-border bg-card p-4">
          {sent}
        </p>
        <Button
          type="button"
          variant="outline"
          className="justify-self-start"
          onClick={() => setSent(null)}
        >
          Send another message
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4 rounded-lg border border-border p-4">
      {canHold ? (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">I&apos;d like to</legend>
          {(
            [
              ["question", "Ask a question"],
              ["hold", "Ask the owner to hold this lot"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="flex items-center gap-2">
              <input
                type="radio"
                name="contact-kind"
                value={value}
                checked={kind === value}
                onChange={() => setKind(value)}
                className="size-4 accent-primary"
              />
              {label}
            </label>
          ))}
        </fieldset>
      ) : null}
      {signedIn?.pending_hold ? (
        <p className="text-sm text-muted-foreground">
          You&apos;ve asked the owner to hold this lot. They&apos;ll reply to {signedIn.email}.
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="contact-name" label="Your name">
          <Input
            id="contact-name"
            required
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </Field>
        {signedIn ? (
          <Field id="contact-email" label="Email">
            <Input id="contact-email" value={signedIn.email} readOnly disabled />
          </Field>
        ) : (
          <Field id="contact-email" label="Email">
            <Input
              id="contact-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
        )}
        <Field id="contact-phone" label="Phone (optional)">
          <Input
            id="contact-phone"
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
          />
        </Field>
      </div>
      <Field id="contact-message" label={holding ? "Message (optional)" : "Your question"}>
        <Textarea
          id="contact-message"
          required={!holding}
          rows={4}
          maxLength={2000}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
        />
      </Field>

      {signedIn ? (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-medium">
            Besides replying, the owner of {subdivisionName} may
          </legend>
          <div className="flex items-center gap-2">
            <Checkbox
              id="allow-email"
              checked={allowEmail}
              onCheckedChange={(checked) => setAllowEmail(checked === true)}
            />
            <Label htmlFor="allow-email" className="font-normal">
              Email me about their lots
            </Label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox
              id="allow-sms"
              checked={allowSms}
              onCheckedChange={(checked) => setAllowSms(checked === true)}
            />
            <Label htmlFor="allow-sms" className="font-normal">
              Text me about their lots (needs a phone number)
            </Label>
          </div>
          <p className="text-xs text-muted-foreground">
            You can change this any time on your account page.
          </p>
        </fieldset>
      ) : buyer.kind === "signed-out" && buyer.turnstileSiteKey ? (
        <Turnstile siteKey={buyer.turnstileSiteKey} onToken={setToken} />
      ) : null}

      <FormMessage error={error} />
      <div className="flex flex-wrap items-center gap-3">
        {/* Offline there's no Turnstile; the question is kept and checked when it's sent. */}
        <Button type="submit" disabled={sending || (!signedIn && !token && online)}>
          {sending ? "Sending…" : holding ? "Request a hold" : "Send question"}
        </Button>
        {signedIn ? null : (
          <p className="text-sm text-muted-foreground">
            <Link href={signInHref} className="underline">
              Sign in
            </Link>{" "}
            to save this lot or ask for a hold.
          </p>
        )}
      </div>
    </form>
  );
}

export function ContactOwner({
  lotLabel,
  subdivisionName,
  available,
}: {
  lotLabel: string;
  subdivisionName: string;
  available: boolean;
}) {
  const { buyer } = useBuyerLot();
  if (buyer.kind === "loading") {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (buyer.kind === "error") {
    return (
      <p role="alert" className="text-sm">
        The contact form couldn&apos;t load. Refresh the page to try again.
      </p>
    );
  }
  // Keyed on who is signed in, so the form's fields start from that person's profile.
  return (
    <ContactForm
      key={buyer.kind === "signed-in" ? buyer.state.email : "signed-out"}
      buyer={buyer}
      lotLabel={lotLabel}
      subdivisionName={subdivisionName}
      available={available}
    />
  );
}
