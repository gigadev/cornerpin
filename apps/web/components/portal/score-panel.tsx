import { formatWhen } from "@/lib/format";
import { modelLabel, reasonEffect, type LeadScore } from "@/lib/scores";
import { RiskBadge } from "./risk-badge";

// A lead's score and the reasons behind it (P3-03; ADR-013, ADR-047). Always marked as advice:
// the owner decides, and the decision is logged with this score.

export function ScorePanel({ score, timeZone }: { score: LeadScore | null; timeZone: string }) {
  return (
    <section
      aria-labelledby="score-heading"
      className="grid gap-3 rounded-lg border border-border bg-card p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="score-heading" className="font-semibold">
          Risk of falling through
        </h2>
        <span className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          Advisory
        </span>
        {score ? <RiskBadge score={score.score} /> : null}
      </div>
      {score ? (
        <>
          <ul className="grid gap-1 text-sm">
            {score.reasons.map((reason) => (
              <li key={reason.code} className="grid grid-cols-[1rem_minmax(0,1fr)] gap-x-2">
                <span aria-hidden="true" className="text-muted-foreground">
                  {reason.weight > 0 ? "↑" : reason.weight < 0 ? "↓" : "·"}
                </span>
                <span>
                  {reason.text}{" "}
                  <span className="text-muted-foreground">({reasonEffect(reason)})</span>
                </span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground">
            From {modelLabel(score.model_version)}, scored{" "}
            {formatWhen(score.scored_at, timeZone)}. It&apos;s a guide only: you make the
            decision, and decisions are logged with the score you saw.
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          Not scored yet. A score appears shortly after the lead&apos;s next activity.
        </p>
      )}
    </section>
  );
}
