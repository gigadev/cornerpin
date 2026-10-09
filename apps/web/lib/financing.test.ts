import { describe, expect, it } from "vitest";
import {
  applicationStatusLabel,
  formatDay,
  formatDollars,
  formatMoney,
  incomeBandLabel,
  loanStanding,
  monthlyPaymentPreview,
  rateLabel,
  termLabel,
} from "./financing";

describe("financing words and numbers", () => {
  it("formats exact amounts", () => {
    expect(formatMoney("1234.5")).toBe("$1,234.50");
    expect(formatMoney("0.00")).toBe("$0.00");
    expect(formatDollars("489000.00")).toBe("$489,000");
  });

  it("formats calendar dates as themselves", () => {
    expect(formatDay("2026-11-01")).toBe("Nov 1, 2026");
    expect(formatDay("2027-02-28")).toBe("Feb 28, 2027");
  });

  it("names terms, rates and income bands", () => {
    expect(termLabel(360)).toBe("30 years");
    expect(termLabel(12)).toBe("1 year");
    expect(termLabel(90)).toBe("90 months");
    expect(rateLabel("0.075")).toBe("7.5%");
    expect(incomeBandLabel("50k_100k")).toBe("$50,000 to $100,000");
  });

  it("previews the same level payment as the API", () => {
    expect(monthlyPaymentPreview(100_000, 0.075, 360).toFixed(2)).toBe("699.21");
    expect(monthlyPaymentPreview(12_000, 0, 12)).toBe(1000);
    expect(monthlyPaymentPreview(0, 0.075, 360)).toBe(0);
  });

  it("says where a loan stands", () => {
    expect(loanStanding({ days_past_due: 0, next_due_on: "2026-11-01" })).toBe("Current");
    expect(loanStanding({ days_past_due: 1, next_due_on: "2026-10-01" })).toBe("1 day behind");
    expect(loanStanding({ days_past_due: 38, next_due_on: "2026-09-01" })).toBe("38 days behind");
    expect(loanStanding({ days_past_due: 0, next_due_on: null })).toBe("Paid off");
  });

  it("names an application's status for buyers and owners", () => {
    expect(applicationStatusLabel("submitted")).toBe("Waiting for a decision");
    expect(applicationStatusLabel("declined")).toBe("Not approved");
  });
});
