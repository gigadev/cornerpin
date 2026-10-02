import Link from "next/link";
import { Button } from "@/components/ui/button";
import { LISTING_TYPES, LOT_STATUSES, listingLabel, statusLabel } from "@/lib/format";
import type { LotFilters } from "@/lib/lot-filters";

// A plain GET form with native controls, so filtering works without JavaScript (P1-07).

const control =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-ring";

export function LotFilterForm({
  action,
  filters,
  phases,
}: {
  action: string;
  filters: LotFilters;
  phases: string[];
}) {
  return (
    <form
      method="get"
      action={action}
      aria-label="Filter lots"
      className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-3 lg:grid-cols-6 lg:items-end"
    >
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Status</span>
        <select name="status" defaultValue={filters.status ?? ""} className={control}>
          <option value="">Any</option>
          {LOT_STATUSES.map((status) => (
            <option key={status} value={status}>
              {statusLabel(status)}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Listing</span>
        <select name="listing" defaultValue={filters.listing ?? ""} className={control}>
          <option value="">Any</option>
          {LISTING_TYPES.map((type) => (
            <option key={type} value={type}>
              {listingLabel(type)}
            </option>
          ))}
        </select>
      </label>
      {phases.length > 1 ? (
        <label className="grid gap-1 text-sm">
          <span className="font-medium">Phase</span>
          <select name="phase" defaultValue={filters.phase ?? ""} className={control}>
            <option value="">Any</option>
            {phases.map((phase) => (
              <option key={phase} value={phase}>
                {phase}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Max price</span>
        <input
          name="max_price"
          inputMode="numeric"
          placeholder="Any"
          defaultValue={filters.maxPrice ?? ""}
          className={control}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium">Min acres</span>
        <input
          name="min_acres"
          inputMode="decimal"
          placeholder="Any"
          defaultValue={filters.minAcres ?? ""}
          className={control}
        />
      </label>
      <div className="col-span-2 flex items-center gap-3 sm:col-span-1">
        <Button type="submit">Show lots</Button>
        <Link href={action} className="text-sm underline">
          Clear
        </Link>
      </div>
    </form>
  );
}
