import { describe, expect, it } from "vitest";
import {
  channelLabel,
  documentLabel,
  formatAcres,
  formatBytes,
  formatPrice,
  formatWhen,
  holdStatusLabel,
  parseDollars,
  parseOptionalNumber,
  statusLabel,
} from "./format";

describe("formatPrice", () => {
  it("shows whole dollars", () => {
    expect(formatPrice(95000)).toBe("$95,000");
    expect(formatPrice(0)).toBe("$0");
  });
  it("says when there is no price", () => {
    expect(formatPrice(null)).toBe("No price");
  });
});

describe("formatAcres", () => {
  it("keeps up to three decimals", () => {
    expect(formatAcres(1.076)).toBe("1.076 ac");
    expect(formatAcres(2)).toBe("2 ac");
    expect(formatAcres(null)).toBe("—");
  });
});

describe("formatWhen", () => {
  it("uses the subdivision's time zone, not the server's", () => {
    const iso = "2026-10-01T20:05:00Z";
    expect(formatWhen(iso, "America/Boise")).toBe("Oct 1, 2026, 2:05 PM MDT");
    expect(formatWhen(iso, "America/Los_Angeles")).toBe("Oct 1, 2026, 1:05 PM PDT");
  });
});

describe("parseDollars", () => {
  it.each([
    ["95000", 95000],
    ["$95,000", 95000],
    [" 1 250 ", 1250],
    ["", null],
  ])("%s -> %s", (given, expected) => {
    expect(parseDollars(given)).toBe(expected);
  });
  it("rejects cents and negatives", () => {
    expect(parseDollars("95000.50")).toBeNaN();
    expect(parseDollars("-5")).toBeNaN();
  });
});

describe("parseOptionalNumber", () => {
  it("treats empty as none", () => {
    expect(parseOptionalNumber("  ")).toBeNull();
    expect(parseOptionalNumber("1.25")).toBe(1.25);
  });
});

describe("statusLabel", () => {
  it("names every status", () => {
    expect(statusLabel("on_hold")).toBe("On hold");
  });
});

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [839_680, "820 KB"],
    [2_516_582, "2.4 MB"],
  ])("%s -> %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("documentLabel", () => {
  it("names every kind", () => {
    expect(documentLabel("covenants")).toBe("Covenants");
  });
});

describe("buyer activity labels", () => {
  it("names channels and hold statuses", () => {
    expect(channelLabel("sms")).toBe("Text messages");
    expect(holdStatusLabel("pending")).toBe("Pending");
  });
});
