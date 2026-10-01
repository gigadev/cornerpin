"use client";

import { useRouter } from "next/navigation";
import { browserApi } from "@/lib/api/browser";

export function SignOutButton() {
  const router = useRouter();

  async function signOut() {
    await browserApi.POST("/v1/auth/signout");
    router.replace("/");
    router.refresh();
  }

  return (
    <button type="button" onClick={signOut} className="underline">
      Sign out
    </button>
  );
}
