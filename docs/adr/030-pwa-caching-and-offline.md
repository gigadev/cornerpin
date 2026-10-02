# ADR-030: PWA caching, offline questions and updates

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-10

## Context

ADR-005 and the plan's PWA table set the behaviour: installable per subdivision, viewed lots
offline, photos cache-first, viewed map tiles cached, queued inquiries, an update prompt, and
nothing private cached. They don't say how to tell public pages from private ones, what "lot
summaries precached on first visit" means for server-rendered pages, how a signed-out
visitor's queued question passes Turnstile, or how scopes work with Next's URLs.

## Decision

- **Public pages are the only pages kept.** One shared rule (`lib/pwa-paths.ts`) decides what a
  public page is: `/{slug}` or `/{slug}/lots/{number}`, where the slug isn't one of the reserved
  words. The service worker keeps those pages' HTML, stale-while-revalidate, and nothing else:
  not `/app`, `/account`, sign-in, the home page (it reads the session), or any API response
  except public photos. Public pages are the same for everyone (ADR-028), so this is safe.
  Other navigations go to the network, with the offline page when that fails.
- **Summaries come with the subdivision page.** The subdivision page already lists every lot
  with its status, price and shape, so it is the summary. Whenever a lot page is kept, the
  worker also keeps its subdivision page. A buyer who scans a sign therefore has the whole
  subdivision offline, not just that lot.
- **Pages a visitor reaches by client-side navigation** are fetched as RSC payloads, which aren't
  kept. A small client component asks the worker to keep each public page visited this way, and
  the first page before the worker took control. Serwist's own `cacheOnNavigation` would also
  re-fetch every portal page, so it stays off.
- **Photos** (originals and Next's optimised copies) are cache-first: at most 150, for 30 days.
  A photo of a lot that is later unpublished can stay on a device that saw it until then.
- **Map tiles** from OpenFreeMap are cache-first: at most 600, for 30 days. Its style is
  stale-while-revalidate. Only tiles the visitor actually viewed are kept, never prefetched:
  OpenFreeMap's terms forbid automated collection but say nothing against caching. MapTiler
  satellite tiles are never cached.
- **Precache.** The build's static files (about 3 MB, under 1 MB compressed) and the offline page
  are precached when the worker installs, so a kept page still runs its scripts offline.
- **Offline page.** It says the visitor is offline and links the pages this device has kept.
- **Queued questions.** A question sent while offline is kept in the browser's storage and sent
  when the connection returns, from whichever Cornerpin page is open. A signed-out visitor's
  question gets a fresh Turnstile check at that point. Background Sync isn't used: Turnstile
  tokens expire and need a page, and Safari has no Background Sync. Hold requests aren't queued.
- **Updates.** A new worker waits; a banner offers "Reload" (or "Later"). Accepting tells it to
  take over and reloads the page.
- **Manifests.** The site, each published subdivision and the owner portal each have a manifest
  with their own `id`, `start_url` and `scope`, linked from their pages. Scopes are written
  without a trailing slash (`/juniper-bench`, `/app`) because Next serves those paths without
  one, and a start URL must be inside its scope. A side effect: `/juniper-bench` also covers a
  slug like `/juniper-bench-ridge`.

## Consequences

- The service worker runs only in production builds; offline behaviour is tested by Playwright
  against `next build && next start`.
- Installing the subdivision app shows that subdivision's pages in the app window.
- A visitor's kept pages can be up to one visit out of date until the network answers.
- Questions queued in a browser that is never opened again are never sent.

## Related

ADR-005 (PWA), ADR-018 (map tiles), ADR-019 (service worker setup), ADR-027 (public pages),
ADR-028 (buyer activity), ADR-029 (push)
