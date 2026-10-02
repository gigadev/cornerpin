import { describe, expect, it } from "vitest";
import { slugify } from "./slug";

describe("slugify", () => {
  it.each([
    ["Juniper Bench", "juniper-bench"],
    ["Juniper Bench, Phase 2", "juniper-bench-phase-2"],
    ["  Sage   Hollow  ", "sage-hollow"],
    ["Café Ridge", "cafe-ridge"],
    ["---", ""],
  ])("%s -> %s", (name, slug) => {
    expect(slugify(name)).toBe(slug);
  });

  it("never ends in a hyphen after trimming to 64 characters", () => {
    const slug = slugify(`${"a".repeat(63)} b`);
    expect(slug.length).toBeLessThanOrEqual(64);
    expect(slug.endsWith("-")).toBe(false);
  });
});
