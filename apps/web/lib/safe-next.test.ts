import { describe, expect, it } from "vitest";
import { SIGNED_IN_HOME, safeNext, signInDestination } from "./safe-next";

describe("signInDestination", () => {
  it.each([
    [undefined, SIGNED_IN_HOME],
    ["", SIGNED_IN_HOME],
    ["/", SIGNED_IN_HOME],
    ["/?ref=sign", SIGNED_IN_HOME],
    ["/signin", SIGNED_IN_HOME],
    ["/signin?next=/signin", SIGNED_IN_HOME],
    ["/auth/verify?token=x", SIGNED_IN_HOME],
    ["//evil.example", SIGNED_IN_HOME],
    ["/app/123", "/app/123"],
    ["/juniper-bench/lots/7", "/juniper-bench/lots/7"],
  ])("%s -> %s", (given, expected) => {
    expect(signInDestination(given)).toBe(expected);
  });
});

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
