import type { DocumentKind, ListingType } from "@/lib/format";

// GraphQL enum values are UPPER_CASE (LOT_AND_HOME); the rest of the app uses the API's
// lower_case values. These convert one to the other; the types make a mismatch a compile error.

export function listingTypeFromGraphql(value: "LAND_ONLY" | "LOT_AND_HOME"): ListingType {
  return value.toLowerCase() as ListingType;
}

export function documentKindFromGraphql(
  value: "PLAT" | "SURVEY" | "COVENANTS" | "UTILITIES" | "OTHER",
): DocumentKind {
  return value.toLowerCase() as DocumentKind;
}
