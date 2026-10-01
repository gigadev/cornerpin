"use client";

import Link from "next/link";
import { useState } from "react";
import { browserApi } from "@/lib/api/browser";
import { safeNext } from "@/lib/safe-next";

export function VerifyForm({ token }: { token: string }) {
  const [state, setState] = useState<"idle" | "working" | "failed">("idle");

  async function signIn() {
    setState("working");
    const { data } = await browserApi.POST("/v1/auth/magic-link/verify", { body: { token } });
    if (data) {
      // A full navigation, so server components render with the new session cookie.
      window.location.assign(safeNext(data.next));
    } else {
      setState("failed");
    }
  }

  if (state === "failed") {
    return (
      <p role="alert" className="mt-4">
        This sign-in link has expired or was already used.{" "}
        <Link href="/signin" className="underline">
          Request a new one
        </Link>
        .
      </p>
    );
  }

  return (
    <button
      type="button"
      onClick={signIn}
      disabled={state === "working"}
      className="mt-6 w-full rounded bg-ink px-4 py-2 font-medium text-surface disabled:opacity-50"
    >
      {state === "working" ? "Signing in…" : "Sign in"}
    </button>
  );
}
