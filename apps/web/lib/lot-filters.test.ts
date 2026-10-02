import { describe, expect, it } from "vitest";
import { applyFilters, hasFilters, parseFilters, type FilterableLot } from "./lot-filters";

const lots: (FilterableLot & { number: string })[] = [
  { number: "1", status: "available", listingType: "land_only", phaseName: "Phase 1", price: 87500, acreage: 1.07 },
  { number: "2", status: "sold", listingType: "land_only", phaseName: "Phase 1", price: 91000, acreage: 1.2 },
  { number: "7", status: "available", listingType: "lot_and_home", phaseName: "Phase 1", price: 549000, acreage: 1.07 },
  { number: "16", status: "available", listingType: "land_only", phaseName: "Phase 2", price: null, acreage: null },
];
const numbers = (selected: { number: string }[]) => selected.map((lot) => lot.number);

describe("parseFilters", () => {
  it("reads known values and ignores the rest", () => {
    expect(
      parseFilters({
        status: "available",
        listing: "lot_and_home",
        phase: " Phase 1 ",
        max_price: "$100,000",
        min_acres: "1",
      }),
    ).toEqual({
      status: "available",
      listing: "lot_and_home",
      phase: "Phase 1",
      maxPrice: 100000,
      minAcres: 1,
    });
    expect(
      parseFilters({ status: "for-sale", listing: "", max_price: "cheap", min_acres: "-2" }),
    ).toEqual({ status: null, listing: null, phase: null, maxPrice: null, minAcres: null });
  });

  it("takes the first of repeated parameters", () => {
    expect(parseFilters({ status: ["sold", "available"] }).status).toBe("sold");
  });
});

describe("applyFilters", () => {
  it("passes everything without filters", () => {
    const none = parseFilters({});
    expect(hasFilters(none)).toBe(false);
    expect(numbers(applyFilters(lots, none))).toEqual(["1", "2", "7", "16"]);
  });

  it("combines filters", () => {
    const filters = parseFilters({ status: "available", phase: "Phase 1", max_price: "100000" });
    expect(hasFilters(filters)).toBe(true);
    expect(numbers(applyFilters(lots, filters))).toEqual(["1"]);
  });

  it("leaves out lots whose price or acreage is unknown when filtering on them", () => {
    expect(numbers(applyFilters(lots, parseFilters({ max_price: "1000000" })))).toEqual([
      "1",
      "2",
      "7",
    ]);
    expect(numbers(applyFilters(lots, parseFilters({ min_acres: "1.1" })))).toEqual(["2"]);
  });

  it("filters homes", () => {
    expect(numbers(applyFilters(lots, parseFilters({ listing: "lot_and_home" })))).toEqual(["7"]);
  });
});
