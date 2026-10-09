import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import {
  bandLabel,
  daysLabel,
  funnelLine,
  monthLong,
  monthShort,
  soldInYear,
  sourceLabel,
  type Dashboard,
} from "@/lib/dashboard";
import { leadStageLabel } from "@/lib/leads";

// A tenant's figures (P3-07, ADR-051): the lead funnel, sales pace, inventory, where leads come
// from, outreach and scores, all from Postgres. One hue throughout; every bar is labelled in
// words, so nothing depends on telling colours apart. Empty states, not errors, for a tenant
// that has nothing yet.

export const metadata: Metadata = { title: "Dashboard · Cornerpin" };

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={`${id}-heading`}
      className="grid content-start gap-3 rounded-xl border border-border bg-card p-4"
    >
      <h2 id={`${id}-heading`} className="font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

/** Horizontal bars, one hue, each with its words and number beside it. */
function BarList({ items }: { items: { key: string; label: string; value: number }[] }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <ul className="grid gap-2">
      {items.map((item) => (
        <li key={item.key} className="grid gap-1" title={`${item.label}: ${item.value}`}>
          <div className="flex justify-between gap-3 text-sm">
            <span>{item.label}</span>
            <span className="tabular-nums text-muted-foreground">{item.value}</span>
          </div>
          <div className="h-2 rounded-full bg-muted" aria-hidden="true">
            <div
              className="h-2 rounded-full bg-primary"
              style={{ width: `${(item.value / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="grid content-start gap-0.5 rounded-xl border border-border bg-card px-4 py-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {detail ? <span className="text-xs text-muted-foreground">{detail}</span> : null}
    </div>
  );
}

function SalesByMonth({ months }: { months: Dashboard["sales_by_month"] }) {
  const max = Math.max(1, ...months.map((month) => month.sold));
  return (
    <div className="grid gap-2">
      <ol className="flex h-36 items-end gap-1" aria-label="Lots sold each month">
        {months.map((month) => (
          <li
            key={month.month}
            className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1"
            title={`${monthLong(month.month)}: ${month.sold} sold`}
          >
            <span className="text-xs tabular-nums text-muted-foreground">
              {month.sold > 0 ? month.sold : ""}
            </span>
            <div
              className="w-full max-w-8 rounded-t-[4px] bg-primary"
              style={{ height: `${(month.sold / max) * 100}%`, minHeight: month.sold ? 4 : 0 }}
            />
            <span className="text-[0.65rem] text-muted-foreground">{monthShort(month.month)}</span>
          </li>
        ))}
      </ol>
      <details className="text-sm">
        <summary className="cursor-pointer text-muted-foreground">As a table</summary>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Month</TableHead>
              <TableHead className="text-right">Sold</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {months.map((month) => (
              <TableRow key={month.month}>
                <TableCell>{monthLong(month.month)}</TableCell>
                <TableCell className="text-right tabular-nums">{month.sold}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </details>
    </div>
  );
}

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const board = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/dashboard", { params: { path: { tenant_id: tenantId } } }),
    `/app/${tenantId}/dashboard`,
  );
  const ladder = board.funnel.filter((stage) => stage.stage !== "lost");
  const lost = board.funnel.find((stage) => stage.stage === "lost");
  const won = ladder.find((stage) => stage.stage === "won");
  const sold = soldInYear(board);
  const scored = board.scores.reduce((total, band) => total + band.leads, 0);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Leads" value={String(board.leads)} />
        <Tile label="Won" value={String(won?.reached ?? 0)} />
        <Tile label="Lots sold" value={String(sold)} detail="in the last 12 months" />
        <Tile
          label="Messages sent"
          value={String(board.outreach.sent)}
          detail={`${board.outreach.replied} replies`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section id="funnel" title="Lead funnel">
          {board.leads === 0 ? (
            <Empty>No leads yet. A lead appears when someone asks about a lot.</Empty>
          ) : (
            <>
              <BarList
                items={ladder.map((stage, i) => ({
                  key: stage.stage,
                  label: funnelLine(stage, ladder[i - 1]),
                  value: stage.reached ?? 0,
                }))}
              />
              <p className="text-sm text-muted-foreground">
                Now: {ladder.map((s) => `${leadStageLabel(s.stage)} ${s.now}`).join(" · ")} ·
                Lost {lost?.now ?? 0}
              </p>
            </>
          )}
        </Section>

        <Section id="sales" title="Lots sold each month">
          {sold === 0 ? (
            <Empty>No lots sold in the last 12 months.</Empty>
          ) : (
            <SalesByMonth months={board.sales_by_month} />
          )}
        </Section>

        <Section id="pace" title="From listing to sold">
          {board.days_to_sold.length === 0 ? (
            <Empty>No lots sold yet.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phase</TableHead>
                  <TableHead className="text-right">Sold</TableHead>
                  <TableHead className="text-right">Median time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {board.days_to_sold.map((phase) => (
                  <TableRow key={`${phase.subdivision_name}-${phase.phase_name}`}>
                    <TableCell>
                      {phase.subdivision_name}, {phase.phase_name}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{phase.sold}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {daysLabel(phase.median_days)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <p className="text-xs text-muted-foreground">
            Listed means added to Cornerpin.
          </p>
        </Section>

        <Section id="inventory" title="Lots by phase">
          {board.inventory.length === 0 ? (
            <Empty>No lots yet.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phase</TableHead>
                  <TableHead className="text-right">Available</TableHead>
                  <TableHead className="text-right">On hold</TableHead>
                  <TableHead className="text-right">Sold</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {board.inventory.map((phase) => (
                  <TableRow key={`${phase.subdivision_name}-${phase.phase_name}`}>
                    <TableCell>
                      {phase.subdivision_name}, {phase.phase_name}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{phase.available}</TableCell>
                    <TableCell className="text-right tabular-nums">{phase.on_hold}</TableCell>
                    <TableCell className="text-right tabular-nums">{phase.sold}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Section>

        <Section id="sources" title="Where leads come from">
          {board.sources.length === 0 ? (
            <Empty>No leads yet.</Empty>
          ) : (
            <BarList
              items={board.sources.map((source) => ({
                key: source.source,
                label: sourceLabel(source.source),
                value: source.leads,
              }))}
            />
          )}
        </Section>

        <Section id="scores" title="Open leads by risk">
          {scored === 0 ? (
            <Empty>No open leads to score.</Empty>
          ) : (
            <>
              <BarList
                items={board.scores.map((band) => ({
                  key: band.band,
                  label: bandLabel(band.band),
                  value: band.leads,
                }))}
              />
              <p className="text-xs text-muted-foreground">
                Advisory scores: a guide, not a decision.
              </p>
            </>
          )}
        </Section>

        <Section id="outreach" title="Outreach">
          <dl className="grid grid-cols-3 gap-3">
            {(
              [
                ["Sent", board.outreach.sent],
                ["Replies", board.outreach.replied],
                ["Handed to a person", board.outreach.handed_off],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="grid gap-0.5">
                <dt className="text-sm text-muted-foreground">{label}</dt>
                <dd className="text-xl font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </Section>
      </div>
    </div>
  );
}
