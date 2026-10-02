import { describe, expect, it } from "vitest";
import { errorMessage } from "./errors";

describe("errorMessage", () => {
  it("uses a plain detail as is", () => {
    expect(errorMessage({ detail: "That web address is already taken" })).toBe(
      "That web address is already taken",
    );
  });

  it("names the field for validation errors", () => {
    expect(
      errorMessage({
        detail: [
          { loc: ["body", "slug"], msg: "Value error, That web address is reserved" },
          { loc: ["body", "time_zone"], msg: "Value error, Not a known time zone" },
        ],
      }),
    ).toBe("slug: That web address is reserved. time zone: Not a known time zone");
  });

  it("falls back for anything else", () => {
    expect(errorMessage(undefined)).toBe("Something went wrong. Try again.");
    expect(errorMessage({ detail: [] }, "Nope")).toBe("Nope");
  });
});
