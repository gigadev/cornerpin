"use client";

import { useState, type FormEvent } from "react";
import { Turnstile } from "@/components/turnstile";
import { browserApi } from "@/lib/api/browser";

type State = "idle" | "sending" | "sent" | "error";

export function SignInForm({
  nextPath,
  turnstileSiteKey,
  googleEnabled,
}: {
  nextPath: string;
  turnstileSiteKey: string;
  googleEnabled: boolean;
}) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<State>("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setState("sending");
    const { response } = await browserApi.POST("/v1/auth/magic-link", {
      body: { email, turnstile_token: token, next: nextPath },
    });
    setState(response.status === 202 ? "sent" : "error");
  }

  if (state === "sent") {
    return (
      <p role="status" className="mt-6 rounded border border-border bg-card p-4">
        Check your email. We sent a sign-in link to <strong>{email}</strong>. It works once and
        expires in 15 minutes.
      </p>
    );
  }

  return (
    <div className="mt-6 space-y-6">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="text-sm font-medium">Email</span>
          <input
            type="email"
            name="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 block w-full rounded border border-border bg-card px-3 py-2"
          />
        </label>
        <Turnstile siteKey={turnstileSiteKey} onToken={setToken} />
        {state === "error" ? (
          <p role="alert" className="text-sm">
            That didn&apos;t work. Check the address and try again.
          </p>
        ) : null}
        <button
          type="submit"
          disabled={!token || state === "sending"}
          className="w-full rounded bg-primary px-4 py-2 font-medium text-primary-foreground disabled:opacity-50"
        >
          {state === "sending" ? "Sending…" : "Email me a sign-in link"}
        </button>
      </form>
      {googleEnabled ? (
        <a
          href={`/v1/auth/google/start?next=${encodeURIComponent(nextPath)}`}
          className="block w-full rounded border border-border bg-card px-4 py-2 text-center font-medium"
        >
          Continue with Google
        </a>
      ) : null}
    </div>
  );
}
