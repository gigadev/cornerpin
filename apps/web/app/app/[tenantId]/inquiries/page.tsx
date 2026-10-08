import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { ContactLine } from "@/components/portal/contact-line";
import Link from "next/link";
import { HoldDecision } from "@/components/portal/hold-decision";
import { RiskBadge } from "@/components/portal/risk-badge";
import { StatusBadge } from "@/components/portal/status-badge";
import { Badge } from "@/components/ui/badge";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import type { components } from "@/lib/api/schema";
import { getMe, serverApi } from "@/lib/api/server";
import { formatWhen, holdStatusLabel } from "@/lib/format";

// Buyers' inquiries and hold requests for one tenant (P1-08). Email alerts for new ones come
// with P1-09; until then this page is where they reach the owner.

type Inquiry = components["schemas"]["InquiryOut"];
type HoldRequest = components["schemas"]["HoldRequestOut"];

const DEFAULT_TIME_ZONE = "America/Boise";

function HoldCard({
  tenantId,
  hold,
  timeZone,
}: {
  tenantId: string;
  hold: HoldRequest;
  timeZone: string;
}) {
  return (
    <li className="grid gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">
          Lot {hold.lot_number}, {hold.subdivision_name}
        </span>
        <StatusBadge status={hold.lot_status} />
        <Badge variant={hold.status === "pending" ? "default" : "outline"}>
          {holdStatusLabel(hold.status)}
        </Badge>
        <span className="text-sm text-muted-foreground sm:ml-auto">
          {formatWhen(hold.created_at, timeZone)}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span>{hold.name}</span>
        {hold.status === "pending" && hold.score ? <RiskBadge score={hold.score.score} /> : null}
        {hold.lead_id ? (
          <Link href={`/app/${tenantId}/leads/${hold.lead_id}`} className="text-sm underline">
            {hold.status === "pending" && hold.score ? "Why this risk?" : "Lead"}
          </Link>
        ) : null}
      </div>
      <ContactLine email={hold.email} phone={hold.phone} signedIn contact={hold.contact} />
      {hold.message ? <p className="whitespace-pre-line">{hold.message}</p> : null}
      {hold.status === "pending" ? (
        <HoldDecision
          tenantId={tenantId}
          holdId={hold.id}
          who={hold.name}
          scoreId={hold.score?.id ?? null}
        />
      ) : null}
    </li>
  );
}

function InquiryCard({ inquiry, timeZone }: { inquiry: Inquiry; timeZone: string }) {
  return (
    <li className="grid gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">
          Lot {inquiry.lot_number}, {inquiry.subdivision_name}
        </span>
        <span className="text-sm text-muted-foreground sm:ml-auto">
          {formatWhen(inquiry.created_at, timeZone)}
        </span>
      </div>
      <p>{inquiry.name}</p>
      <ContactLine
        email={inquiry.email}
        phone={inquiry.phone}
        signedIn={inquiry.signed_in}
        contact={inquiry.contact}
      />
      <p className="whitespace-pre-line">{inquiry.message}</p>
    </li>
  );
}

export default async function InquiriesPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const tenant = await getTenant(tenantId);
  const me = await getMe();
  const timeZone = me?.time_zone ?? DEFAULT_TIME_ZONE;
  const api = await serverApi();
  const path = `/app/${tenantId}/inquiries`;
  const options = { params: { path: { tenant_id: tenantId } } };
  const [holds, inquiries] = await Promise.all([
    loadOr404(api.GET("/v1/tenants/{tenant_id}/hold-requests", options), path),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/inquiries", options), path),
  ]);

  return (
    <div className="grid gap-8">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">Inquiries and holds</h1>

      <section aria-labelledby="holds-heading" className="grid gap-3">
        <h2 id="holds-heading" className="text-lg font-semibold">
          Hold requests
        </h2>
        <p className="text-sm text-muted-foreground">
          Approving a request puts an available lot on hold.
        </p>
        {holds.length === 0 ? (
          <p className="text-muted-foreground">No hold requests yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {holds.map((hold) => (
              <HoldCard key={hold.id} tenantId={tenantId} hold={hold} timeZone={timeZone} />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="inquiries-heading" className="grid gap-3">
        <h2 id="inquiries-heading" className="text-lg font-semibold">
          Inquiries
        </h2>
        {inquiries.length === 0 ? (
          <p className="text-muted-foreground">No inquiries yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {inquiries.map((inquiry) => (
              <InquiryCard key={inquiry.id} inquiry={inquiry} timeZone={timeZone} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
