import type { MultiPolygon } from "geojson";
import { describe, expect, it } from "vitest";
import {
  STATUS_COLORS,
  boundsOf,
  firstPolygon,
  lotFeatures,
  lotStatusFromGraphql,
  satelliteStyle,
} from "./lots";

const square = (west: number, south: number): MultiPolygon => ({
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [west, south],
        [west + 1, south],
        [west + 1, south + 1],
        [west, south + 1],
        [west, south],
      ],
    ],
  ],
});

describe("lotFeatures", () => {
  it("maps lots with shapes and leaves the rest off", () => {
    const collection = lotFeatures([
      { id: "a", number: "1", status: "available", boundary: square(0, 0) },
      { id: "b", number: "2", status: "sold", boundary: null },
      { id: "c", number: "3", status: "on_hold", boundary: square(2, 0) },
    ]);
    expect(collection.features.map((f) => f.properties.number)).toEqual(["1", "3"]);
    expect(collection.features[1]?.properties.color).toBe(STATUS_COLORS.on_hold);
    expect(collection.features[0]?.id).toBe("a");
  });
});

describe("boundsOf", () => {
  it("covers every shape", () => {
    const collection = lotFeatures([
      { id: "a", number: "1", status: "available", boundary: square(-116.4, 43.4) },
      { id: "b", number: "2", status: "available", boundary: square(-116.2, 43.6) },
    ]);
    expect(boundsOf(collection)).toEqual([-116.4, 43.4, -115.2, 44.6]);
  });

  it("is null without shapes", () => {
    expect(boundsOf({ type: "FeatureCollection", features: [] })).toBeNull();
  });
});

describe("firstPolygon", () => {
  it("takes the first part of a multipolygon", () => {
    expect(firstPolygon(square(0, 0))?.coordinates[0]?.[2]).toEqual([1, 1]);
    expect(firstPolygon({ type: "MultiPolygon", coordinates: [] })).toBeNull();
  });
});

describe("lotStatusFromGraphql", () => {
  it("lowercases GraphQL enum values", () => {
    expect(lotStatusFromGraphql("ON_HOLD")).toBe("on_hold");
  });
});

describe("satelliteStyle", () => {
  it("puts the key in the URL, escaped", () => {
    expect(satelliteStyle("a b")).toContain("key=a%20b");
  });
});
