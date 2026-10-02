import { notFound, redirect } from "next/navigation";
import { publicQuery } from "@/lib/graphql/client";
import { QrTargetDocument } from "@/lib/graphql/generated";
import { QR_CODE_PATTERN } from "@/lib/qr";

// Where a printed sign's QR code lands (P1-11, ADR-031). The code names a lot; its current
// address is looked up on every scan, so signs survive slug renames. The redirect is temporary
// (307), so no browser remembers an old address.
export const dynamic = "force-dynamic";

export default async function QrRedirect({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  if (!QR_CODE_PATTERN.test(code)) notFound();
  const { qrTarget } = await publicQuery(QrTargetDocument, { code });
  if (!qrTarget) notFound();
  redirect(`/${qrTarget.subdivisionSlug}/lots/${encodeURIComponent(qrTarget.lotNumber)}`);
}
