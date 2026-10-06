import { describe, expect, it } from "vitest";
import { installNotice, slackSummary, type Integration } from "./integrations";

const slack: Integration = {
  provider: "slack",
  available: true,
  status: "connected",
  enabled: true,
  workspace: "Demo Land Co.",
  channel: "#lots",
  error: null,
};

describe("slackSummary", () => {
  it("says where alerts go and whether they're on", () => {
    expect(slackSummary(slack)).toBe("Connected. Alerts on: #lots in Demo Land Co.");
    expect(slackSummary({ ...slack, enabled: false })).toBe(
      "Connected. Alerts off (/lot still answers): #lots in Demo Land Co.",
    );
    expect(slackSummary({ ...slack, channel: null, workspace: null })).toBe(
      "Connected. Alerts on.",
    );
  });

  it("explains every other state", () => {
    expect(slackSummary({ ...slack, status: "connecting" })).toMatch(/^Connecting to Slack/);
    expect(slackSummary({ ...slack, status: "failed", error: "Slack said no" })).toBe(
      "Slack said no",
    );
    expect(slackSummary({ ...slack, status: "not_connected" })).toBe("Not connected.");
    expect(slackSummary({ ...slack, status: "not_connected", available: false })).toBe(
      "Slack isn't set up on this Cornerpin yet.",
    );
  });
});

describe("installNotice", () => {
  it("reads what Slack sent back", () => {
    expect(installNotice("cancelled")).toBe("Slack wasn't added.");
    expect(installNotice("connecting")).toMatch(/^Slack sent you back/);
    expect(installNotice(undefined)).toBeNull();
  });
});
