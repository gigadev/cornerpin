import type { components } from "@/lib/api/schema";

// Advisory risk scores in the owner portal (P3-03; ADR-013, ADR-045, ADR-047): how a lead's risk
// of falling through reads, and how a logged decision describes the score that was shown.

export type LeadScore = components["schemas"]["LeadScore"];
export type ScoreReason = components["schemas"]["ScoreReason"];
export type DecisionKind = components["schemas"]["LeadDecision"]["kind"];
export type RiskBand = "low" | "medium" | "high";

/** Below a third is low, above two thirds high. */
export function riskBand(score: number): RiskBand {
  if (score < 1 / 3) return "low";
  return score > 2 / 3 ? "high" : "medium";
}

export function riskPercent(score: number): string {
  return `${Math.round(score * 100)}%`;
}

const BAND_LABELS: Record<RiskBand, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export function riskLabel(score: number): string {
  return BAND_LABELS[riskBand(score)];
}

export function reasonEffect(reason: ScoreReason): string {
  if (reason.weight > 0) return "raises the risk";
  if (reason.weight < 0) return "lowers the risk";
  return "no effect";
}

/** Where a score came from, said plainly. */
export function modelLabel(version: string): string {
  if (version.startsWith("lgbm-")) {
    return `a model (${version.slice("lgbm-".length)}) trained on synthetic data`;
  }
  if (version.startsWith("rules-")) return "the starting rules";
  return version;
}

/** The score as it stood when a decision was made, in a line for the timeline. */
export function shownScore(score: LeadScore | null | undefined): string {
  if (!score) return "No score was shown.";
  const reasons = score.reasons
    .slice(0, 3)
    .map((reason) => reason.text)
    .join("; ");
  const risk = `Risk shown: ${riskPercent(score.score)}, ${riskLabel(score.score).toLowerCase()}`;
  return reasons ? `${risk} (${reasons}).` : `${risk}.`;
}

const DECISIONS: Record<DecisionKind, string> = {
  hold_approved: "approved the hold",
  hold_declined: "declined the hold",
  lead_won: "marked the lead won",
  lead_lost: "marked the lead lost",
};

export function decisionTitle(kind: DecisionKind | undefined, lot: string | null): string {
  if (!kind) return "Decision";
  const what = DECISIONS[kind];
  return lot && kind.startsWith("hold_") ? `Decision: ${what} on ${lot}` : `Decision: ${what}`;
}
