"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { Field, FormMessage } from "./field";

// What an owner does in the financing demo (P3-06, ADR-050): decide an application, logged with
// the score on screen, and record a payment received.

export function ApplicationDecision({
  tenantId,
  applicationId,
  who,
  scoreId,
}: {
  tenantId: string;
  applicationId: string;
  who: string;
  /** The score shown beside the application, logged with the decision. */
  scoreId: string | null;
}) {
  const router = useRouter();
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reasonId = `decline-reason-${applicationId}`;

  async function decide(decision: "approve" | "decline") {
    setBusy(true);
    setError(null);
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/financing/applications/{application_id}/decision",
      {
        params: { path: { tenant_id: tenantId, application_id: applicationId } },
        body: { decision, reason, score_id: scoreId },
      },
    );
    setBusy(false);
    if (failure) setError(errorMessage(failure));
    else router.refresh();
  }

  function submitDecline(event: FormEvent) {
    event.preventDefault();
    void decide("decline");
  }

  if (declining) {
    return (
      <form onSubmit={submitDecline} className="grid gap-2">
        <Field id={reasonId} label="Why not? The buyer is shown this.">
          <Textarea
            id={reasonId}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
            maxLength={500}
            rows={2}
          />
        </Field>
        <div className="flex gap-2">
          <Button type="submit" size="sm" variant="destructive" disabled={busy || !reason.trim()}>
            Decline
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setDeclining(false)}>
            Cancel
          </Button>
        </div>
        <FormMessage error={error} />
      </form>
    );
  }

  return (
    <div className="grid gap-1">
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={busy}
          onClick={() => void decide("approve")}
          aria-label={`Approve financing for ${who}`}
        >
          Approve
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => setDeclining(true)}
          aria-label={`Decline financing for ${who}`}
        >
          Decline
        </Button>
      </div>
      <FormMessage error={error} />
    </div>
  );
}

export function RecordPayment({
  tenantId,
  loanId,
  suggested,
  today,
}: {
  tenantId: string;
  loanId: string;
  /** The monthly payment, as an exact two-decimal string. */
  suggested: string;
  today: string;
}) {
  const router = useRouter();
  const [amount, setAmount] = useState(suggested);
  const [paidOn, setPaidOn] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDone(null);
    const { error: failure } = await browserApi.POST(
      "/v1/tenants/{tenant_id}/financing/loans/{loan_id}/payments",
      {
        params: { path: { tenant_id: tenantId, loan_id: loanId } },
        body: { amount, paid_on: paidOn },
      },
    );
    setBusy(false);
    if (failure) {
      setError(errorMessage(failure));
      return;
    }
    setDone("Payment recorded.");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="grid gap-3 rounded-xl border border-border bg-card p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="payment-amount" label="Amount">
          <Input
            id="payment-amount"
            inputMode="decimal"
            pattern="^\d+(\.\d{1,2})?$"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            required
          />
        </Field>
        <Field id="payment-date" label="Received on">
          <Input
            id="payment-date"
            type="date"
            max={today}
            value={paidOn}
            onChange={(event) => setPaidOn(event.target.value)}
            required
          />
        </Field>
      </div>
      <FormMessage error={error} success={done} />
      <div>
        <Button type="submit" disabled={busy}>
          Record payment
        </Button>
      </div>
    </form>
  );
}
