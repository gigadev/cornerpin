import { describe, expect, it } from "vitest";
import { safeNext } from "./safe-next";

describe("safeNext", () => {
  it.each([
    ["/app", "/app"],
    ["/juniper-bench/lots/7?x=1", "/juniper-bench/lots/7?x=1"],
    [null, "/"],
    [undefined, "/"],
    ["", "/"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["app", "/"],
  ])("%s -> %s", (given, expected) => {
    expect(safeNext(given)).toBe(expected);
  });
});
