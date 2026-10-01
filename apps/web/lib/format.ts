import type { components } from "@/lib/api/schema";

export type LotStatus = components["schemas"]["LotStatus"];
export type ListingType = components["schemas"]["ListingType"];
export type ReleaseStatus = components["schemas"]["ReleaseStatus"];

export const LOT_STATUSES: readonly LotStatus[] = ["available", "on_hold", "sold"];
export const LISTING_TYPES: readonly ListingType[] = ["land_only", "lot_and_home"];
export const RELEASE_STATUSES: readonly ReleaseStatus[] = ["upcoming", "released"];

const STATUS_LABELS: Record<LotStatus, string> = {
  available: "Available",
  on_hold: "On hold",
  sold: "Sold",
};

const LISTING_LABELS: Record<ListingType, string> = {
  land_only: "Land only",
  lot_and_home: "Lot + home",
};

const RELEASE_LABELS: Record<ReleaseStatus, string> = {
  upcoming: "Upcoming",
  released: "Released",
};

export function statusLabel(status: LotStatus): string {
  return STATUS_LABELS[status];
}

export function listingLabel(type: ListingType): string {
  return LISTING_LABELS[type];
}

export function releaseLabel(status: ReleaseStatus): string {
  return RELEASE_LABELS[status];
}

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

export function formatPrice(price: number | null | undefined): string {
  return price === null || price === undefined ? "No price" : dollars.format(price);
}

export function formatAcres(acres: number | null | undefined): string {
  if (acres === null || acres === undefined) return "—";
  return `${acres.toLocaleString("en-US", { maximumFractionDigits: 3 })} ac`;
}

/** A timestamp in the subdivision's time zone, e.g. "Oct 1, 2026, 2:05 PM MDT". */
export function formatWhen(iso: string, timeZone: string): string {
  // dateStyle/timeStyle cannot be combined with timeZoneName, so the parts are spelled out.
  // Newer ICU puts a narrow no-break space before AM/PM; a plain space reads the same.
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone,
    timeZoneName: "short",
  })
    .format(new Date(iso))
    .replace(/ /g, " ");
}

/** Whole dollars from a form field; empty means no price. */
export function parseDollars(value: string): number | null {
  const cleaned = value.replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  const parsed = Number(cleaned);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : Number.NaN;
}

/** An optional number from a form field; empty means none. */
export function parseOptionalNumber(value: string): number | null {
  if (value.trim() === "") return null;
  return Number(value);
}
