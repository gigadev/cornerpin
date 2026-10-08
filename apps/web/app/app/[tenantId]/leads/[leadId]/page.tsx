import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { ContactLine } from "@/components/portal/contact-line";
import { LeadNoteForm, LeadStageSelect, ResolveHandoff } from "@/components/portal/lead-actions";
import { LeadStageBadge } from "@/components/portal/lead-stage-badge";
import { ScorePanel } from "@/components/portal/score-panel";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { getMe, serverApi } from "@/lib/api/server";
import { formatWhen } from "@/lib/format";
import { describeEvent, eventActor } from "@/lib/leads";

// One lead (P2-02, ADR-035): who they are, what they allow, everything that has happened, the
// owner's stage, notes and handoff, and its advisory score (P3-03, ADR-047).

export const metadata: Metadata = { title: "Lead · Cornerpin" };

const DEFAULT_TIME_ZONE = "America/Boise";

const SOURCES: Record<string, string> = {
  inquiry: "a question",
  hold_request: "a hold request",
  account: "their account page",
};

export default async function LeadPage({
  params,
}: {
  params: Promise<{ tenantId: string; leadId: string }>;
}) {
  const { tenantId, leadId } = await params;
  const tenant = await getTenant(tenantId);
  const me = await getMe();
  const timeZone = me?.time_zone ?? DEFAULT_TIME_ZONE;
  const api = await serverApi();
  const lead = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/leads/{lead_id}", {
      params: { path: { tenant_id: tenantId, lead_id: leadId } },
    }),
    `/app/${tenantId}/leads/${leadId}`,
  );
  const name = lead.name || lead.email;

  return (
    <div className="grid gap-8">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          { href: `/app/${tenantId}/leads`, label: "Leads" },
        ]}
      />

      <div className="grid gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{name}</h1>
          <LeadStageBadge stage={lead.stage} />
        </div>
        <ContactLine
          email={lead.email}
          phone={lead.phone}
          signedIn={lead.signed_in}
          contact={lead.contact}
        />
        <p className="text-sm text-muted-foreground">
          First came through {SOURCES[lead.source] ?? lead.source} on{" "}
          {formatWhen(lead.created_at, timeZone)}.
        </p>
        {lead.lots.length > 0 ? (
          <p className="text-sm">
            {lead.lots.map((lot) => `Lot ${lot.number}, ${lot.subdivision_name}`).join(" · ")}
          </p>
        ) : null}
      </div>

      {lead.handoff_at ? (
        <section
          aria-labelledby="handoff-heading"
          className="grid gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4"
        >
          <h2 id="handoff-heading" className="font-semibold">
            Needs a person
          </h2>
          <p className="text-sm">
            Since {formatWhen(lead.handoff_at, timeZone)}
            {lead.handoff_reason ? `: ${lead.handoff_reason}` : "."}
          </p>
          <div>
            <ResolveHandoff tenantId={tenantId} leadId={lead.id} />
          </div>
        </section>
      ) : null}

      {lead.stage === "won" || lead.stage === "lost" ? null : (
        <ScorePanel score={lead.score ?? null} timeZone={timeZone} />
      )}

      <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
        <div className="grid content-start gap-6">
          <LeadStageSelect
            tenantId={tenantId}
            leadId={lead.id}
            stage={lead.stage}
            scoreId={lead.score?.id ?? null}
          />
          <LeadNoteForm tenantId={tenantId} leadId={lead.id} />
        </div>

        <section aria-labelledby="timeline-heading" className="grid content-start gap-3">
          <h2 id="timeline-heading" className="text-lg font-semibold">
            Timeline
          </h2>
          <ol className="divide-y divide-border rounded-lg border border-border">
            {lead.events.map((event) => {
              const { title, body } = describeEvent(event);
              return (
                <li key={event.id} className="grid gap-1 px-4 py-3">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="font-medium">{title}</span>
                    <span className="text-sm text-muted-foreground sm:ml-auto">
                      {eventActor(event, name)} · {formatWhen(event.created_at, timeZone)}
                    </span>
                  </div>
                  {body ? <p className="whitespace-pre-line">{body}</p> : null}
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </div>
  );
}
