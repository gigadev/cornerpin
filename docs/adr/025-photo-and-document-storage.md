# ADR-025: Photo and document storage

- **Status:** Accepted
- **Date:** 2026-10-01
- **Applies from:** P1-05

## Context

P1-05 puts photo and document uploads behind a storage interface backed by local disk and
Cloud Storage (ADR-009). The plan does not say which files are accepted, what happens to
photo metadata, how files are served, or how files are cleaned up when their rows go.

## Decision

- **One interface, two backends.** `cornerpin.core.storage` stores bytes by key, such as
  `tenants/<tenant>/lots/<lot>/photos/<id>.jpg`. Locally the files live in the gitignored
  `var/storage` folder; Playwright runs use `var/e2e-storage` and pytest a temporary folder. The
  Cloud Storage backend is written but dormant until `STORAGE_BACKEND=gcs` and `STORAGE_BUCKET`
  exist. Keys are checked so they cannot escape the storage root.
- **Photos are re-encoded on upload.** JPEG, PNG and WebP up to 15 MB. Each is decoded, turned
  upright from its camera rotation flag, stripped of all metadata (phone photos carry GPS
  position and device details), scaled so its longest side is at most 2560 px, and saved again
  in its own format.
- **Documents are stored as uploaded.** PDF, JPEG and PNG up to 25 MB, identified by their
  first bytes rather than the browser's claim. A download is named after the document's title.
- **Files are served through the API.** The portal fetches `/v1/tenants/{tenant}/photos/{id}/file`
  and `/documents/{id}/file` after the same membership check as everything else. Photos are
  cacheable by the browser only (`private`, immutable); documents are not cached. Public serving
  for published lots arrives with the public pages in P1-07.
- **Removing a file goes through the outbox.** Deleting a photo, a document or a lot queues a
  `storage.object_removed` event in the same transaction, and the worker removes the file. A
  rolled-back delete leaves the file alone; a failed removal is retried. Signed-in users may now
  queue outbox events (migration 0005), except `auth.*` events, which stay with sign-in.
- **Reordering sends the whole order.** The portal sends every photo id in its new position;
  the API refuses a list that misses or repeats one.

## Consequences

- Photos are safe to publish as uploaded: no location leaks, no sideways pictures.
- An upload that fails after its file is written takes the file back out; a crash between the
  two can leave an orphan file, which is harmless.
- Uploads are buffered in the API before checking, so the size limits are also the memory cost.
  Cloud Run's 32 MB request limit sits above both.
- The service worker must never cache `/v1/tenants/*` responses (ADR-005); P1-10 adds the rule.

## Related

ADR-005 (PWA caching), ADR-009 (Cloud Storage), ADR-010 (outbox), ADR-024 (portal rules)
