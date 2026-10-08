import { Badge } from "@/components/ui/badge";
import { riskBand, riskLabel, riskPercent, type RiskBand } from "@/lib/scores";

// A lead's advisory risk of falling through, at a glance (P3-03, ADR-047).

const BAND_CLASSES: Record<RiskBand, string> = {
  low: "border-transparent bg-status-available-soft text-status-available",
  medium: "border-transparent bg-status-hold-soft text-status-hold",
  high: "border-transparent bg-destructive/10 text-destructive",
};

export function RiskBadge({ score }: { score: number }) {
  return (
    <Badge
      variant="outline"
      className={BAND_CLASSES[riskBand(score)]}
      title="Risk of falling through: advice, not a decision"
    >
      {riskLabel(score)} · {riskPercent(score)}
    </Badge>
  );
}
