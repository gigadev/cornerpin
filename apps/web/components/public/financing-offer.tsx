"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Field, FormMessage } from "@/components/portal/field";
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
import type { components } from "@/lib/api/schema";
import { errorMessage } from "@/lib/api/errors";
import {
  formatDollars,
  formatMoney,
  incomeBandLabel,
  monthlyPaymentPreview,
  rateLabel,
  termLabel,
  type IncomeBand,
  type Term,
} from "@/lib/financing";
import { useBuyerLot } from "./buyer-lot";

// Owner financing on a lot page (P3-06, ADR-050): a demonstration with synthetic terms, shown
// only when the lot's owner has the demo on. No SSN, no date of birth, no credit check.

type Offer = components["schemas"]["FinancingOffer"];

function isTerm(offer: Offer, value: string): value is `${Term}` {
  return offer.terms.some((term) => String(term) === value);
}

function isBand(offer: Offer, value: string): value is IncomeBand {
  return offer.income_bands.some((band) => band === value);
}

function ApplyForm({ offer, initialName }: { offer: Offer; initialName: string }) {
  const { lotId } = useBuyerLot();
  const price = Number(offer.price);
  const [name, setName] = useState(initialName);
  const [down, setDown] = useState(String(Math.ceil(price * 0.2)));
  const [term, setTerm] = useState<Term>(360);
  const [band, setBand] = useState<IncomeBand | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const downPayment = Number(down) || 0;
  const monthly = monthlyPaymentPreview(price - downPayment, Number(offer.annual_rate), term);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!band) {
      setError("Choose an income band");
      return;
    }
    setBusy(true);
    setError(null);
    const { error: failure } = await browserApi.POST("/v1/lots/{lot_id}/financing-applications", {
      params: { path: { lot_id: lotId } },
      body: { name, down_payment: downPayment, term_months: term, income_band: band },
    });
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else setSent(true);
  }

  if (sent) {
    return (
      <p role="status" className="rounded-xl border border-border bg-card p-5">
        Application sent. The owner will decide; you&apos;ll see it on{" "}
        <Link href="/account" className="underline">
          your account page
        </Link>
        .
      </p>
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4 rounded-xl border border-border bg-card p-5">
      <Field id="financing-name" label="Name on the application">
        <Input
          id="financing-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={120}
        />
      </Field>
      <Field
        id="financing-down"
        label="Down payment (whole dollars)"
        hint={`Between ${formatDollars(offer.min_down)} and ${formatDollars(offer.max_down)}`}
      >
        <Input
          id="financing-down"
          type="number"
          inputMode="numeric"
          min={Number(offer.min_down)}
          max={Number(offer.max_down)}
          step={1}
          value={down}
          onChange={(event) => setDown(event.target.value)}
          required
        />
      </Field>
      <Field id="financing-term" label="Term">
        <Select
          value={String(term)}
          onValueChange={(value) => {
            if (isTerm(offer, value)) setTerm(Number(value) as Term);
          }}
        >
          <SelectTrigger id="financing-term" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {offer.terms.map((months) => (
              <SelectItem key={months} value={String(months)}>
                {termLabel(months)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field
        id="financing-income"
        label="Yearly income (a range)"
        hint="Stated, never checked. It's compared with the payment, nothing else."
      >
        <Select
          value={band}
          onValueChange={(value) => {
            if (isBand(offer, value)) setBand(value);
          }}
        >
          <SelectTrigger id="financing-income" className="w-full">
            <SelectValue placeholder="Choose a range" />
          </SelectTrigger>
          <SelectContent>
            {offer.income_bands.map((option) => (
              <SelectItem key={option} value={option}>
                {incomeBandLabel(option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <p className="text-sm">
        About <strong>{formatMoney(monthly.toFixed(2))} a month</strong> at{" "}
        {rateLabel(offer.annual_rate)} over {termLabel(term)}, borrowing{" "}
        {formatDollars(Math.max(price - downPayment, 0))}.
      </p>
      <FormMessage error={error} />
      <div>
        <Button type="submit" disabled={busy}>
          Apply to finance this lot
        </Button>
      </div>
    </form>
  );
}

export function FinancingOffer() {
  const { lotId, signInHref, buyer } = useBuyerLot();
  const [offer, setOffer] = useState<Offer | null>(null);

  useEffect(() => {
    let current = true;
    browserApi
      .GET("/v1/lots/{lot_id}/financing", { params: { path: { lot_id: lotId } } })
      .then(({ data }) => {
        if (current && data) setOffer(data);
      })
      .catch(() => {
        // Offline or unavailable: the offer simply doesn't show.
      });
    return () => {
      current = false;
    };
  }, [lotId]);

  if (!offer) return null;
  return (
    <section aria-labelledby="financing-heading" className="grid scroll-mt-4 gap-3">
      <h2 id="financing-heading" className="text-2xl font-semibold tracking-tight">
        Owner financing <span className="text-base font-normal text-muted-foreground">(demo)</span>
      </h2>
      <p className="max-w-prose text-sm text-muted-foreground">
        A demonstration with made-up terms: {rateLabel(offer.annual_rate)} a year, 5 to 30 years.
        It asks for no Social Security number, no date of birth and no credit check, so
        don&apos;t enter real financial details.
      </p>
      {buyer.kind === "signed-in" ? (
        <ApplyForm offer={offer} initialName={buyer.state.display_name ?? ""} />
      ) : buyer.kind === "signed-out" ? (
        <p>
          <Link href={signInHref} className="underline">
            Sign in to apply
          </Link>
          .
        </p>
      ) : null}
    </section>
  );
}
