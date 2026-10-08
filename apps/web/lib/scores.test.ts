import { describe, expect, it } from "vitest";
import {
  decisionTitle,
  modelLabel,
  reasonEffect,
  riskBand,
  riskLabel,
  riskPercent,
  shownScore,
  type LeadScore,
} from "./scores";

const score: LeadScore = {
  id: "s1",
  score: 0.292,
  model_version: "lgbm-lead-v1",
  scored_at: "2026-10-07T18:00:00Z",
  reasons: [
    { code: "hold_requests", text: "Asked to hold a lot", weight: -0.86 },
    { code: "touches", text: "1 message sent", weight: -0.317 },
    { code: "stage", text: "In conversation", weight: -0.148 },
    { code: "replies", text: "Replied only once", weight: 0.118 },
  ],
};

describe("risk", () => {
  it("bands at thirds", () => {
    expect([0, 0.33, 0.34, 0.66, 0.67, 1].map(riskBand)).toEqual([
      "low",
      "low",
      "medium",
      "medium",
      "high",
      "high",
    ]);
  });

  it("reads as a percentage and a band", () => {
    expect(riskPercent(0.292)).toBe("29%");
    expect(riskLabel(0.88)).toBe("High risk");
  });

  it("says which way each reason pushed", () => {
    expect(score.reasons.map(reasonEffect)).toEqual([
      "lowers the risk",
      "lowers the risk",
      "lowers the risk",
      "raises the risk",
    ]);
    expect(reasonEffect({ code: "x", text: "x", weight: 0 })).toBe("no effect");
  });

  it("names the model plainly, and says the data is synthetic", () => {
    expect(modelLabel("lgbm-lead-v1")).toBe("a model (lead-v1) trained on synthetic data");
    expect(modelLabel("rules-v1")).toBe("the starting rules");
  });
});

describe("decisions", () => {
  it("describe the score that was shown, with its top three reasons", () => {
    expect(shownScore(score)).toBe(
      "Risk shown: 29%, low risk (Asked to hold a lot; 1 message sent; In conversation).",
    );
    expect(shownScore(null)).toBe("No score was shown.");
  });

  it("say what was decided, and on which lot for a hold", () => {
    expect(decisionTitle("hold_approved", "Lot 3-1, Juniper Bench")).toBe(
      "Decision: approved the hold on Lot 3-1, Juniper Bench",
    );
    expect(decisionTitle("lead_lost", null)).toBe("Decision: marked the lead lost");
    expect(decisionTitle(undefined, null)).toBe("Decision");
  });
});
