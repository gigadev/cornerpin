import { describe, expect, it } from "vitest";
import {
  bandLabel,
  daysLabel,
  funnelLine,
  monthLong,
  monthShort,
  percent,
  soldInYear,
  sourceLabel,
  type Dashboard,
} from "./dashboard";

describe("dashboard words", () => {
  it("names months as themselves, whatever the time zone", () => {
    expect(monthShort("2026-03-01")).toBe("Mar");
    expect(monthLong("2025-11-01")).toBe("November 2025");
  });

  it("describes the funnel step by step", () => {
    const contacted = { stage: "contacted", now: 1, reached: 2, conversion: null } as const;
    const engaged = { stage: "engaged", now: 0, reached: 1, conversion: 0.5 } as const;
    expect(funnelLine(contacted, undefined)).toBe("Contacted: 2 reached");
    expect(funnelLine(engaged, contacted)).toBe("Engaged: 1 reached, 50% of contacted");
    expect(percent(2 / 3)).toBe("67%");
  });

  it("reads days to sold in plain terms", () => {
    expect(daysLabel(1)).toBe("1 day");
    expect(daysLabel(45.4)).toBe("45 days");
    expect(daysLabel(213)).toBe("about 7 months");
  });

  it("names sources and score bands", () => {
    expect(sourceLabel("hold_request")).toBe("A hold request");
    expect(sourceLabel("something_new")).toBe("something_new");
    expect(bandLabel("unscored")).toBe("Not scored yet");
  });

  it("adds up a year of sales", () => {
    const board = {
      sales_by_month: [
        { month: "2026-01-01", sold: 2 },
        { month: "2026-02-01", sold: 0 },
        { month: "2026-03-01", sold: 1 },
      ],
    } as Dashboard;
    expect(soldInYear(board)).toBe(3);
  });
});
