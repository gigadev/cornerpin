import { Badge } from "@/components/ui/badge";
import { leadStageLabel, type LeadStage } from "@/lib/leads";

const VARIANTS = {
  new: "default",
  contacted: "secondary",
  engaged: "secondary",
  holding: "secondary",
  won: "outline",
  lost: "ghost",
} as const satisfies Record<LeadStage, "default" | "secondary" | "outline" | "ghost">;

export function LeadStageBadge({ stage }: { stage: LeadStage }) {
  return <Badge variant={VARIANTS[stage]}>{leadStageLabel(stage)}</Badge>;
}
