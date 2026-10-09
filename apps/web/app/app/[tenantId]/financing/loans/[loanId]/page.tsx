import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { RecordPayment } from "@/components/portal/financing-actions";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { getMe, serverApi } from "@/lib/api/server";
import { formatDay, formatMoney, loanStanding, rateLabel, termLabel } from "@/lib/financing";

// One loan in the financing demo (P3-06, ADR-050): where it stands, its payments, a form to
// record one, and its whole amortization schedule, to the cent.

export const metadata: Metadata = { title: "Loan · Cornerpin" };

const DEFAULT_TIME_ZONE = "America/Boise";

function today(timeZone: string): string {
  // en-CA formats as YYYY-MM-DD, the date input's own format.
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date());
}

export default async function LoanPage({
  params,
}: {
  params: Promise<{ tenantId: string; loanId: string }>;
}) {
  const { tenantId, loanId } = await params;
  const tenant = await getTenant(tenantId);
  const me = await getMe();
  const timeZone = me?.time_zone ?? DEFAULT_TIME_ZONE;
  const api = await serverApi();
  const loan = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/financing/loans/{loan_id}", {
      params: { path: { tenant_id: tenantId, loan_id: loanId } },
    }),
    `/app/${tenantId}/financing/loans/${loanId}`,
  );
  const facts: [string, string][] = [
    ["Borrowed", formatMoney(loan.principal)],
    ["Terms", `${termLabel(loan.term_months)} at ${rateLabel(loan.annual_rate)}`],
    ["Monthly payment", formatMoney(loan.monthly_payment)],
    ["Paid to date", formatMoney(loan.paid_to_date)],
    ["Still owed", formatMoney(loan.outstanding_balance)],
    ["Past due", formatMoney(loan.past_due)],
    ["Standing", loanStanding(loan)],
    ["Next due", loan.next_due_on ? formatDay(loan.next_due_on) : "Nothing; paid off"],
  ];

  return (
    <div className="grid gap-8">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          { href: `/app/${tenantId}/financing`, label: "Financing" },
        ]}
      />
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{loan.applicant_name}</h1>
        <p className="text-muted-foreground">
          Lot {loan.lot_number}, {loan.subdivision_name}. Synthetic data, for the demo.
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="grid gap-0.5">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="payments-heading" className="grid gap-3">
        <h2 id="payments-heading" className="text-lg font-semibold">
          Payments
        </h2>
        {loan.payments.length === 0 ? (
          <p className="text-muted-foreground">No payments yet.</p>
        ) : (
          <ol className="divide-y divide-border rounded-xl border border-border bg-card text-sm">
            {loan.payments.map((payment) => (
              <li key={payment.id} className="flex flex-wrap gap-x-4 px-4 py-2">
                <span className="tabular-nums">{formatDay(payment.paid_on)}</span>
                <span className="font-medium tabular-nums">{formatMoney(payment.amount)}</span>
                <span className="text-muted-foreground sm:ml-auto">
                  {payment.recorded_by_email ?? "synthetic seed"}
                </span>
              </li>
            ))}
          </ol>
        )}
        {loan.next_due_on ? (
          <RecordPayment
            tenantId={tenantId}
            loanId={loan.id}
            suggested={loan.monthly_payment}
            today={today(timeZone)}
          />
        ) : null}
      </section>

      <section aria-labelledby="schedule-heading" className="grid gap-3">
        <h2 id="schedule-heading" className="text-lg font-semibold">
          Schedule
        </h2>
        <div className="max-h-[32rem] overflow-auto rounded-xl border border-border bg-card">
          <Table>
            <TableHeader className="sticky top-0 bg-card">
              <TableRow>
                <TableHead className="text-right">#</TableHead>
                <TableHead>Due</TableHead>
                <TableHead className="text-right">Payment</TableHead>
                <TableHead className="text-right">Principal</TableHead>
                <TableHead className="text-right">Interest</TableHead>
                <TableHead className="text-right">Balance after</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loan.schedule.map((row) => (
                <TableRow key={row.number}>
                  <TableCell className="text-right tabular-nums">{row.number}</TableCell>
                  <TableCell className="tabular-nums">{formatDay(row.due_on)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatMoney(row.payment)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoney(row.principal)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMoney(row.interest)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatMoney(row.balance)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
