import { describe, expect, it } from "vitest";
import { isLotPage, isPublicPage, publicPage, subdivisionOf } from "./pwa-paths";

describe("publicPage", () => {
  it("knows subdivision and lot pages", () => {
    expect(publicPage("/juniper-bench")).toEqual({ slug: "juniper-bench", lot: null });
    expect(publicPage("/juniper-bench/lots/7")).toEqual({ slug: "juniper-bench", lot: "7" });
    expect(publicPage("/juniper-bench/lots/A-12")).toEqual({ slug: "juniper-bench", lot: "A-12" });
  });

  it.each([
    "/",
    "/app",
    "/app/957ccd5e-b6d1-531f-a102-ddef309c396e",
    "/account",
    "/signin",
    "/auth/verify",
    "/offline",
    "/v1/me",
    "/_next/static/chunk.js",
    "/juniper-bench/opengraph-image",
    "/juniper-bench/manifest.webmanifest",
    "/juniper-bench/lots",
    "/juniper-bench/lots/7/extra",
    "/Juniper-Bench",
  ])("never treats %s as a public page", (path) => {
    expect(isPublicPage(path)).toBe(false);
  });
});

describe("subdivisionOf", () => {
  it("finds a lot page's subdivision", () => {
    expect(subdivisionOf("/juniper-bench/lots/7")).toBe("/juniper-bench");
    expect(subdivisionOf("/juniper-bench")).toBeNull();
    expect(subdivisionOf("/app/x/lots/7")).toBeNull();
  });
});

describe("isLotPage", () => {
  it("is true only for lot pages", () => {
    expect(isLotPage("/juniper-bench/lots/7")).toBe(true);
    expect(isLotPage("/juniper-bench")).toBe(false);
  });
});
