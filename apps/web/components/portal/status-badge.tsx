import { Badge } from "@/components/ui/badge";
import { statusLabel, type LotStatus } from "@/lib/format";

const VARIANTS = {
  available: "default",
  on_hold: "secondary",
  sold: "outline",
} as const satisfies Record<LotStatus, "default" | "secondary" | "outline">;

export function StatusBadge({ status }: { status: LotStatus }) {
  return <Badge variant={VARIANTS[status]}>{statusLabel(status)}</Badge>;
}

export function PublishedBadge({ published }: { published: boolean }) {
  return published ? (
    <Badge variant="outline">Published</Badge>
  ) : (
    <Badge variant="ghost">Draft</Badge>
  );
}
