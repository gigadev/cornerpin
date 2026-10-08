import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { ContactLine } from "@/components/portal/contact-line";
import { LeadStageBadge } from "@/components/portal/lead-stage-badge";
import { RiskBadge } from "@/components/portal/risk-badge";
import { Badge } from "@/components/ui/badge";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import type { components } from "@/lib/api/schema";
import { getMe, serverApi } from "@/lib/api/server";
import { formatWhen } from "@/lib/format";
import { isLeadStage, leadStageLabel, type LeadStage } from "@/lib/leads";

// A tenant's leads (P2-02, ADR-035): one per buyer, newest activity first, by stage or only those
// waiting for a person. Links are plain query strings, so filtering works without JavaScript.

export const metadata: Metadata = { title: "Leads · Cornerpin" };

type Lead = components["schemas"]["LeadSummary"];

const DEFAULT_TIME_ZONE = "America/Boise";

type Filter = { stage: LeadStage | null; needsHuman: boolean };

function filterHref(tenantId: string, filter: Partial<Filter>): string {
  const query = new URLSearchParams();
  if (filter.stage) query.set("stage", filter.stage);
  if (filter.needsHuman) query.set("needs_human", "true");
  const search = query.toString();
  return `/app/${tenantId}/leads${search ? `?${search}` : ""}`;
}

function FilterLink({
  href,
  current,
  children,
}: {
  href: string;
  current: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={`rounded-full border px-3 py-1 text-sm ${
        current
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border hover:bg-muted"
      }`}
    >
      {children}
    </Link>
  );
}

function LeadCard({ tenantId, lead, timeZone }: { tenantId: string; lead: Lead; timeZone: string }) {
  return (
    <li className="grid gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/app/${tenantId}/leads/${lead.id}`} className="font-medium underline">
          {lead.name || lead.email}
        </Link>
        <LeadStageBadge stage={lead.stage} />
        {lead.score && lead.stage !== "won" && lead.stage !== "lost" ? (
          <RiskBadge score={lead.score.score} />
        ) : null}
        {lead.handoff_at ? <Badge variant="destructive">Needs a person</Badge> : null}
        <span className="text-sm text-muted-foreground sm:ml-auto">
          {formatWhen(lead.last_activity_at, timeZone)}
        </span>
      </div>
      <ContactLine
        email={lead.email}
        phone={lead.phone}
        signedIn={lead.signed_in}
        contact={lead.contact}
      />
      {lead.lots.length > 0 ? (
        <p className="text-sm">
          {lead.lots.map((lot) => `Lot ${lot.number}, ${lot.subdivision_name}`).join(" · ")}
        </p>
      ) : null}
      {lead.handoff_reason ? (
        <p className="text-sm text-muted-foreground">{lead.handoff_reason}</p>
      ) : null}
    </li>
  );
}

export default async function LeadsPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ stage?: string; needs_human?: string }>;
}) {
  const { tenantId } = await params;
  const query = await searchParams;
  const filter: Filter = {
    stage: isLeadStage(query.stage) ? query.stage : null,
    needsHuman: query.needs_human === "true",
  };
  const tenant = await getTenant(tenantId);
  const me = await getMe();
  const timeZone = me?.time_zone ?? DEFAULT_TIME_ZONE;
  const api = await serverApi();
  const list = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/leads", {
      params: {
        path: { tenant_id: tenantId },
        query: { stage: filter.stage, needs_human: filter.needsHuman },
      },
    }),
    filterHref(tenantId, filter),
  );
  const total = list.stages.reduce((sum, stage) => sum + stage.count, 0);
  const all = filter.stage === null && !filter.needsHuman;

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
      <p className="max-w-prose text-muted-foreground">
        Everyone who has asked about a lot or asked to hold one, one entry per person.
      </p>

      <nav aria-label="Filter leads" className="flex flex-wrap gap-2">
        <FilterLink href={filterHref(tenantId, {})} current={all}>
          All ({total})
        </FilterLink>
        <FilterLink
          href={filterHref(tenantId, { needsHuman: true })}
          current={filter.needsHuman}
        >
          Needs a person ({list.needs_human})
        </FilterLink>
        {list.stages.map(({ stage, count }) => (
          <FilterLink
            key={stage}
            href={filterHref(tenantId, { stage })}
            current={filter.stage === stage}
          >
            {leadStageLabel(stage)} ({count})
          </FilterLink>
        ))}
      </nav>

      <section aria-label="Leads" className="grid gap-3">
        {list.leads.length === 0 ? (
          <p className="text-muted-foreground">
            {filter.needsHuman
              ? "Nobody is waiting for a person."
              : all
                ? "No leads yet. They appear when someone asks about a lot."
                : "No leads at this stage."}
          </p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {list.leads.map((lead) => (
              <LeadCard key={lead.id} tenantId={tenantId} lead={lead} timeZone={timeZone} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
