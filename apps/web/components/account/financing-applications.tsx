import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { components } from "@/lib/api/schema";
import { formatWhen } from "@/lib/format";
import {
  applicationStatusLabel,
  formatDollars,
  formatMoney,
  rateLabel,
  termLabel,
} from "@/lib/financing";

// A buyer's financing applications on the demo tenant (P3-06, ADR-050), with the decision and,
// on a decline, its principal reasons in the shape of an adverse-action notice.

type Application = components["schemas"]["MyApplication"];

function DeclineNotice({ application }: { application: Application }) {
  const decision = application.decision;
  if (!decision || decision.kind !== "declined") return null;
  return (
    <div
      role="note"
      aria-label="Why it wasn't approved"
      className="grid gap-2 rounded-lg border border-border bg-muted/40 p-3 text-sm"
    >
      <p className="font-medium">Notice: financing not approved</p>
      <p>The owner&apos;s reason: {decision.reason}</p>
      {decision.principal_reasons.length > 0 ? (
        <div className="grid gap-1">
          <p>The principal reasons, from the risk score the owner saw:</p>
          <ol className="list-decimal pl-5">
            {decision.principal_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ol>
        </div>
      ) : null}
      <p className="text-muted-foreground">
        This is a demonstration. A real notice would also tell you the lender&apos;s name and your
        rights under the Equal Credit Opportunity Act.
      </p>
    </div>
  );
}

export function FinancingApplications({
  applications,
  timeZone,
}: {
  applications: Application[];
  timeZone: string;
}) {
  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-card">
      {applications.map((application) => {
        const lot = application.lot_number
          ? `Lot ${application.lot_number}, ${application.subdivision_name}`
          : "A lot no longer listed";
        return (
          <li key={application.id} className="grid gap-2 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              {application.subdivision_slug && application.lot_number ? (
                <Link
                  href={`/${application.subdivision_slug}/lots/${encodeURIComponent(application.lot_number)}`}
                  className="font-medium underline-offset-4 hover:underline"
                >
                  {lot}
                </Link>
              ) : (
                <span className="font-medium">{lot}</span>
              )}
              <Badge variant={application.status === "submitted" ? "default" : "outline"}>
                {applicationStatusLabel(application.status)}
              </Badge>
              <span className="text-sm text-muted-foreground sm:ml-auto">
                {formatWhen(application.created_at, timeZone)}
              </span>
            </div>
            <p className="text-sm">
              Borrowing {formatDollars(application.amount)} with{" "}
              {formatDollars(application.down_payment)} down over{" "}
              {termLabel(application.term_months)} at {rateLabel(application.annual_rate)}: about{" "}
              {formatMoney(application.monthly_payment)} a month.
            </p>
            <DeclineNotice application={application} />
          </li>
        );
      })}
    </ul>
  );
}
