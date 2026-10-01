/// <reference lib="esnext" />
/// <reference lib="webworker" />
import { Serwist } from "serwist";

// Deliberately empty: no precache and no runtime caching. The caching rules, offline fallback
// and queued inquiries arrive in P1-10, and authenticated and /app responses are never cached.
const serwist = new Serwist({
  skipWaiting: true,
  clientsClaim: true,
});

serwist.addEventListeners();
