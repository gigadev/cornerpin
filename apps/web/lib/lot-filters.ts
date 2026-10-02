import type { ListingType, LotStatus } from "@/lib/format";
import { LISTING_TYPES, LOT_STATUSES } from "@/lib/format";

// Filters for the public lot list. They live in the query string, so the filter form works as a
// plain GET form without JavaScript and a filtered list can be shared as a link.

export type LotFilters = {
  status: LotStatus | null;
  listing: ListingType | null;
  phase: string | null;
  maxPrice: number | null;
  minAcres: number | null;
};

export type FilterableLot = {
  status: LotStatus;
  listingType: ListingType;
  phaseName: string;
  price: number | null;
  acreage: number | null;
};

type SearchParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function positiveNumber(value: string): number | null {
  const parsed = Number(value.replace(/[$,\s]/g, ""));
  return value !== "" && Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function oneOf<T extends string>(options: readonly T[], value: string): T | null {
  return (options as readonly string[]).includes(value) ? (value as T) : null;
}

/** Filters from a page's search params; anything unrecognised is ignored. */
export function parseFilters(params: SearchParams): LotFilters {
  return {
    status: oneOf(LOT_STATUSES, first(params.status)),
    listing: oneOf(LISTING_TYPES, first(params.listing)),
    phase: first(params.phase) || null,
    maxPrice: positiveNumber(first(params.max_price)),
    minAcres: positiveNumber(first(params.min_acres)),
  };
}

export function hasFilters(filters: LotFilters): boolean {
  return Object.values(filters).some((value) => value !== null);
}

/** Lots that pass every filter. Lots with no price never pass a price limit, and lots with no
 * acreage never pass an acreage minimum: the buyer asked for something they can't confirm. */
export function applyFilters<T extends FilterableLot>(lots: readonly T[], filters: LotFilters): T[] {
  return lots.filter(
    (lot) =>
      (filters.status === null || lot.status === filters.status) &&
      (filters.listing === null || lot.listingType === filters.listing) &&
      (filters.phase === null || lot.phaseName === filters.phase) &&
      (filters.maxPrice === null || (lot.price !== null && lot.price <= filters.maxPrice)) &&
      (filters.minAcres === null || (lot.acreage !== null && lot.acreage >= filters.minAcres)),
  );
}
