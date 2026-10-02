"use client";

import { PageCacher } from "./page-cacher";
import { QueuedInquiries } from "./queued-inquiries";
import { UpdatePrompt } from "./update-prompt";

/** The app's offline helpers (ADR-030), on every page: banners stack at the bottom. */
export function PwaClient() {
  return (
    <>
      <PageCacher />
      <div className="pointer-events-none fixed inset-x-4 bottom-4 z-50 mx-auto grid max-w-md gap-2 [&>*]:pointer-events-auto">
        <QueuedInquiries />
        <UpdatePrompt />
      </div>
    </>
  );
}
