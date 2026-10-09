import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { ApplicationDecision } from "@/components/portal/financing-actions";
import { RiskBadge } from "@/components/portal/risk-badge";
import { ScoreReasons } from "@/components/portal/score-panel";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import type { components } from "@/lib/api/schema";
import { getMe, serverApi } from "@/lib/api/server";
import { formatWhen } from "@/lib/format";
import {
  applicationStatusLabel,
  formatDollars,
  formatMoney,
  incomeBandLabel,
  loanStanding,
  termLabel,
} from "@/lib/financing";
import { modelLabel } from "@/lib/scores";

// The owner-financing demo (P3-05, P3-06; ADR-049, ADR-050): applications with their advisory
// scores and decisions, loans that are behind, and every loan. Synthetic data, demo tenant only;
// the API answers 404 anywhere else, and so does this page.

export const metadata: Metadata = { title: "Financing · Cornerpin" };

type Application = components["schemas"]["ApplicationOut"];
const DEFAULT_TIME_ZONE = "America/Boise";

function ApplicationCard({
  tenantId,
  application,
  timeZone,
}: {
  tenantId: string;
  application: Application;
  timeZone: string;
}) {
  const price = Number(application.amount) + Number(application.down_payment);
  const downShare = Math.round((Number(application.down_payment) / price) * 100);
  const decision = application.decision;
  return (
    <li className="grid gap-2 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{application.applicant_name}</span>
        <Badge variant={application.status === "submitted" ? "default" : "outline"}>
          {applicationStatusLabel(application.status)}
        </Badge>
        {application.status === "submitted" && application.score ? (
          <RiskBadge score={application.score.score} />
        ) : null}
        <span className="text-sm text-muted-foreground sm:ml-auto">
          {formatWhen(application.created_at, timeZone)}
        </span>
      </div>
      <p className="text-sm">
        Lot {application.lot_number}, {application.subdivision_name}:{" "}
        {formatDollars(application.amount)} over {termLabel(application.term_months)} with{" "}
        {formatDollars(application.down_payment)} down ({downShare}%). Stated income:{" "}
        {incomeBandLabel(application.income_band)}.
      </p>
      {application.status === "submitted" ? (
        <>
          {application.score ? (
            <div className="grid gap-1">
              <p className="text-sm font-medium">
                Risk of falling behind{" "}
                <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
                  Advisory
                </span>
              </p>
              <ScoreReasons reasons={application.score.reasons} />
              <p className="text-xs text-muted-foreground">
                From {modelLabel(application.score.model_version)}. You decide; the decision is
                logged with this score.
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Not scored yet; refresh in a moment.</p>
          )}
          <ApplicationDecision
            tenantId={tenantId}
            applicationId={application.id}
            who={application.applicant_name}
            scoreId={application.score?.id ?? null}
          />
        </>
      ) : decision ? (
        <div className="grid gap-1 text-sm">
          <p>
            {decision.kind === "approved" ? "Approved" : "Declined"}: {decision.reason}{" "}
            <span className="text-muted-foreground">
              ({decision.decided_by_email ?? "synthetic seed"},{" "}
              {formatWhen(decision.decided_at, timeZone)})
            </span>
          </p>
          {decision.principal_reasons.length > 0 ? (
            <p className="text-muted-foreground">
              Principal reasons given: {decision.principal_reasons.join("; ")}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export default async function FinancingPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const tenant = await getTenant(tenantId);
  const me = await getMe();
  const timeZone = me?.time_zone ?? DEFAULT_TIME_ZONE;
  const api = await serverApi();
  const path = `/app/${tenantId}/financing`;
  const options = { params: { path: { tenant_id: tenantId } } };
  const [applications, loans] = await Promise.all([
    loadOr404(api.GET("/v1/tenants/{tenant_id}/financing/applications", options), path),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/financing/loans", options), path),
  ]);
  const behind = loans.filter((loan) => loan.days_past_due > 0);

  return (
    <div className="grid gap-8">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <div className="grid gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Financing <span className="text-lg font-normal text-muted-foreground">(demo)</span>
        </h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          A demonstration on synthetic data: what an owner who finances lots would see. The
          applicants marked &ldquo;(synthetic)&rdquo; are made up, and nothing here is real
          lending.
        </p>
      </div>

      <section aria-labelledby="applications-heading" className="grid gap-3">
        <h2 id="applications-heading" className="text-lg font-semibold">
          Applications
        </h2>
        {applications.length === 0 ? (
          <p className="text-muted-foreground">No applications yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border bg-card">
            {applications.map((application) => (
              <ApplicationCard
                key={application.id}
                tenantId={tenantId}
                application={application}
                timeZone={timeZone}
              />
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="behind-heading" className="grid gap-3">
        <h2 id="behind-heading" className="text-lg font-semibold">
          Behind on payments
        </h2>
        {behind.length === 0 ? (
          <p className="text-muted-foreground">Every loan is up to date.</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-destructive/40 bg-card">
            {behind.map((loan) => (
              <li key={loan.id} className="flex flex-wrap items-center gap-2 px-4 py-3">
                <Link
                  href={`/app/${tenantId}/financing/loans/${loan.id}`}
                  className="font-medium underline"
                >
                  {loan.applicant_name}
                </Link>
                <span className="text-sm">
                  Lot {loan.lot_number}: {formatMoney(loan.past_due)} past due
                </span>
                <Badge variant="destructive" className="sm:ml-auto">
                  {loanStanding(loan)}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="loans-heading" className="grid gap-3">
        <h2 id="loans-heading" className="text-lg font-semibold">
          Loans
        </h2>
        {loans.length === 0 ? (
          <p className="text-muted-foreground">No loans yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Borrower</TableHead>
                  <TableHead className="hidden sm:table-cell">Lot</TableHead>
                  <TableHead className="text-right">Monthly</TableHead>
                  <TableHead className="text-right">Still owed</TableHead>
                  <TableHead>Standing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loans.map((loan) => (
                  <TableRow key={loan.id}>
                    <TableCell>
                      <Link
                        href={`/app/${tenantId}/financing/loans/${loan.id}`}
                        className="underline"
                      >
                        {loan.applicant_name}
                      </Link>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">{loan.lot_number}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMoney(loan.monthly_payment)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMoney(loan.outstanding_balance)}
                    </TableCell>
                    <TableCell>{loanStanding(loan)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </div>
  );
}
