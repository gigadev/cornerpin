import type { components } from "@/lib/api/schema";
import { formatPrice, formatWhen, statusLabel } from "@/lib/format";

type Lot = components["schemas"]["LotDetail"];

function Who({ email, at, timeZone }: { email: string | null; at: string; timeZone: string }) {
  return (
    <span className="text-muted-foreground">
      {email ?? "System"} · <time dateTime={at}>{formatWhen(at, timeZone)}</time>
    </span>
  );
}

/** Status and price history, newest first, in the subdivision's time zone. */
export function LotHistory({ lot }: { lot: Lot }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <section aria-labelledby="status-history">
        <h3 id="status-history" className="mb-2 text-sm font-medium">
          Status changes
        </h3>
        <ol className="grid gap-2 text-sm">
          {lot.status_history.map((change) => (
            <li key={`${change.changed_at}-${change.to_status}`} className="grid">
              <span>
                {change.from_status
                  ? `${statusLabel(change.from_status)} → ${statusLabel(change.to_status)}`
                  : `Listed as ${statusLabel(change.to_status)}`}
              </span>
              <Who email={change.changed_by_email} at={change.changed_at} timeZone={lot.time_zone} />
            </li>
          ))}
        </ol>
      </section>
      <section aria-labelledby="price-history">
        <h3 id="price-history" className="mb-2 text-sm font-medium">
          Price changes
        </h3>
        <ol className="grid gap-2 text-sm">
          {lot.price_history.map((change) => (
            <li key={`${change.changed_at}-${change.to_price ?? "none"}`} className="grid">
              <span>
                {change.from_price === null && change.to_price === null
                  ? "No price"
                  : change.from_price === null
                    ? `Priced at ${formatPrice(change.to_price)}`
                    : `${formatPrice(change.from_price)} → ${formatPrice(change.to_price)}`}
              </span>
              <Who email={change.changed_by_email} at={change.changed_at} timeZone={lot.time_zone} />
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
