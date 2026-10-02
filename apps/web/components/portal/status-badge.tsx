import { Badge } from "@/components/ui/badge";
import { statusLabel, type LotStatus } from "@/lib/format";

// The same hues as the map (ADR-026), as tokens in globals.css.
const TONES = {
  available: "bg-status-available-soft text-status-available",
  on_hold: "bg-status-hold-soft text-status-hold",
  sold: "bg-status-sold-soft text-status-sold",
} as const satisfies Record<LotStatus, string>;

export function StatusBadge({ status }: { status: LotStatus }) {
  return (
    <Badge variant="outline" className={`border-transparent ${TONES[status]}`}>
      <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
      {statusLabel(status)}
    </Badge>
  );
}

export function PublishedBadge({ published }: { published: boolean }) {
  return published ? (
    <Badge variant="outline">Published</Badge>
  ) : (
    <Badge variant="ghost">Draft</Badge>
  );
}
