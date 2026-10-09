import type { components } from "@/lib/api/schema";

// The owner-financing demo (P3-05, P3-06; ADR-049, ADR-050): how its terms, money and loans
// read. Amounts arrive from the API as exact two-decimal strings ("1234.50").

export type IncomeBand = components["schemas"]["ApplicationCreate"]["income_band"];
export type Term = components["schemas"]["ApplicationCreate"]["term_months"];
export type LoanSummary = components["schemas"]["LoanSummary"];

const MONEY = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const WHOLE = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/** "1234.5" or 1234.5 → "$1,234.50". */
export function formatMoney(amount: string | number): string {
  return MONEY.format(Number(amount));
}

export function formatDollars(amount: string | number): string {
  return WHOLE.format(Number(amount));
}

const DAY = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

/** A calendar date, "2026-11-01" → "Nov 1, 2026"; read as itself, never shifted by a time zone. */
export function formatDay(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  return DAY.format(new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1)));
}

/** 360 → "30 years", 90 → "90 months". */
export function termLabel(months: number): string {
  if (months % 12 !== 0) return `${months} months`;
  const years = months / 12;
  return years === 1 ? "1 year" : `${years} years`;
}

/** "0.075" → "7.5%". */
export function rateLabel(rate: string | number): string {
  return `${(Number(rate) * 100).toLocaleString("en-US", { maximumFractionDigits: 3 })}%`;
}

const INCOME: Record<IncomeBand, string> = {
  under_50k: "Under $50,000",
  "50k_100k": "$50,000 to $100,000",
  "100k_150k": "$100,000 to $150,000",
  over_150k: "Over $150,000",
};

export function incomeBandLabel(band: IncomeBand): string {
  return INCOME[band];
}

/** The level monthly payment, for the form's preview only; the API's figures are exact. */
export function monthlyPaymentPreview(principal: number, annualRate: number, months: number): number {
  if (principal <= 0 || months <= 0) return 0;
  const rate = annualRate / 12;
  if (rate === 0) return principal / months;
  const factor = (1 + rate) ** months;
  return (principal * rate * factor) / (factor - 1);
}

/** Where a loan stands, in a word or two. */
export function loanStanding(loan: Pick<LoanSummary, "days_past_due" | "next_due_on">): string {
  if (loan.days_past_due > 0) {
    return loan.days_past_due === 1 ? "1 day behind" : `${loan.days_past_due} days behind`;
  }
  return loan.next_due_on ? "Current" : "Paid off";
}

const STATUS: Record<components["schemas"]["ApplicationOut"]["status"], string> = {
  submitted: "Waiting for a decision",
  approved: "Approved",
  declined: "Not approved",
  withdrawn: "Withdrawn",
};

export function applicationStatusLabel(
  status: components["schemas"]["ApplicationOut"]["status"],
): string {
  return STATUS[status];
}
