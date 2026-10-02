"use client";

import { useRouter } from "next/navigation";
import { browserApi } from "@/lib/api/browser";
import { unsubscribeDevice } from "@/lib/push-client";

export function SignOutButton() {
  const router = useRouter();

  async function signOut() {
    // This device's push alerts belong to the person signing out (ADR-029).
    await unsubscribeDevice();
    await browserApi.POST("/v1/auth/signout");
    router.replace("/");
    router.refresh();
  }

  return (
    <button type="button" onClick={signOut} className="cursor-pointer">
      Sign out
    </button>
  );
}
