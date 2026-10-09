import type { components } from "@/lib/api/schema";
import { leadStageLabel } from "@/lib/leads";

// The owner dashboard (P3-07, ADR-051): how its figures read.

export type Dashboard = components["schemas"]["Dashboard"];
export type FunnelStage = components["schemas"]["FunnelStage"];

const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
const MONTH_YEAR = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function utc(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1));
}

/** "2026-03-01" → "Mar". */
export function monthShort(isoDate: string): string {
  return MONTH.format(utc(isoDate));
}

/** "2026-03-01" → "March 2026". */
export function monthLong(isoDate: string): string {
  return MONTH_YEAR.format(utc(isoDate));
}

export function percent(share: number): string {
  return `${Math.round(share * 100)}%`;
}

/** "Engaged: 2 reached, 67% of contacted". */
export function funnelLine(stage: FunnelStage, previous: FunnelStage | undefined): string {
  const name = leadStageLabel(stage.stage);
  const reached = stage.reached ?? 0;
  if (!previous || stage.conversion === null) return `${name}: ${reached} reached`;
  return `${name}: ${reached} reached, ${percent(stage.conversion)} of ${leadStageLabel(previous.stage).toLowerCase()}`;
}

/** Whole days, "about 7 months" past 60. */
export function daysLabel(days: number): string {
  const whole = Math.round(days);
  if (whole === 1) return "1 day";
  if (whole < 60) return `${whole} days`;
  return `about ${Math.round(whole / 30.4)} months`;
}

const SOURCES: Record<string, string> = {
  inquiry: "A question",
  hold_request: "A hold request",
  account: "Their account page",
};

export function sourceLabel(source: string): string {
  return SOURCES[source] ?? source;
}

const BANDS: Record<components["schemas"]["ScoreBand"]["band"], string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
  unscored: "Not scored yet",
};

export function bandLabel(band: components["schemas"]["ScoreBand"]["band"]): string {
  return BANDS[band];
}

export function soldInYear(board: Dashboard): number {
  return board.sales_by_month.reduce((total, month) => total + month.sold, 0);
}
