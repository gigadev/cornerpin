// Web push in the browser (ADR-029): is it possible here, and subscribe or unsubscribe this
// device. The service worker only runs in production builds, so locally push needs
// `pnpm build && pnpm start` (see docs/TEST_ACCOUNTS.md).

import { browserApi } from "@/lib/api/browser";
import { applicationServerKey } from "@/lib/push-message";

export type DevicePush =
  | { state: "off-site" } // push isn't configured on the server
  | { state: "unsupported" }
  | { state: "blocked" }
  | { state: "off" | "on"; key: string; registration: ServiceWorkerRegistration };

export async function devicePush(): Promise<DevicePush> {
  const { data } = await browserApi.GET("/v1/push/config");
  const key = data?.public_key ?? null;
  if (!key) return { state: "off-site" };
  const supported =
    "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  if (!supported) return { state: "unsupported" };
  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration) return { state: "unsupported" };
  if (Notification.permission === "denied") return { state: "blocked" };
  const subscription = await registration.pushManager.getSubscription();
  return { state: subscription ? "on" : "off", key, registration };
}

/** Ask permission, subscribe this device and register it with the API. */
export async function subscribeDevice(
  key: string,
  registration: ServiceWorkerRegistration,
): Promise<"on" | "blocked" | "failed"> {
  if ((await Notification.requestPermission()) !== "granted") return "blocked";
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: applicationServerKey(key),
  });
  const { endpoint, keys } = subscription.toJSON();
  if (!endpoint || !keys?.p256dh || !keys.auth) return "failed";
  const { response } = await browserApi.PUT("/v1/me/push-subscriptions", {
    body: { endpoint, keys: { p256dh: keys.p256dh, auth: keys.auth } },
  });
  if (!response.ok) {
    await subscription.unsubscribe();
    return "failed";
  }
  return "on";
}

/** Stop alerts on this device. Also used on sign-out, so the next person to sign in here
 * doesn't get the last one's alerts. Never throws. */
export async function unsubscribeDevice(): Promise<void> {
  try {
    const registration = await navigator.serviceWorker?.getRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return;
    await browserApi.DELETE("/v1/me/push-subscriptions", {
      params: { query: { endpoint: subscription.endpoint } },
    });
    await subscription.unsubscribe();
  } catch {
    // Nothing to clean up, or the browser refused; the push service will expire it.
  }
}
