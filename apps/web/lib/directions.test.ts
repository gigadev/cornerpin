import { describe, expect, it } from "vitest";
import { directionsUrl } from "./directions";

describe("directionsUrl", () => {
  it("puts latitude first, to six places", () => {
    expect(directionsUrl(-116.38608041, 43.40220427)).toBe(
      "https://www.google.com/maps/dir/?api=1&destination=43.402204%2C-116.386080",
    );
  });
});
