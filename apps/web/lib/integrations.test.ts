import { describe, expect, it } from "vitest";
import {
  installNotice,
  salesforceSummary,
  slackSummary,
  toggleLabel,
  type Integration,
} from "./integrations";

const slack: Integration = {
  provider: "slack",
  available: true,
  status: "connected",
  enabled: true,
  account: "Demo Land Co.",
  channel: "#lots",
  error: null,
};

const salesforce: Integration = {
  provider: "salesforce",
  available: true,
  status: "connected",
  enabled: true,
  account: "cornerpin-dev.develop.my.salesforce.com",
  channel: null,
  error: null,
};

describe("slackSummary", () => {
  it("says where alerts go and whether they're on", () => {
    expect(slackSummary(slack)).toBe("Connected. Alerts on: #lots in Demo Land Co.");
    expect(slackSummary({ ...slack, enabled: false })).toBe(
      "Connected. Alerts off (/lot still answers): #lots in Demo Land Co.",
    );
    expect(slackSummary({ ...slack, channel: null, account: null })).toBe(
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

describe("salesforceSummary", () => {
  it("names the org and whether it's syncing", () => {
    expect(salesforceSummary(salesforce)).toBe(
      "Connected. Syncing: cornerpin-dev.develop.my.salesforce.com",
    );
    expect(salesforceSummary({ ...salesforce, enabled: false })).toMatch(/^Connected\. Syncing is off/);
    expect(salesforceSummary({ ...salesforce, status: "connecting" })).toMatch(/sending your lots/);
    expect(salesforceSummary({ ...salesforce, status: "failed", error: "Bad key" })).toBe(
      "Bad key",
    );
  });

  it("labels the switch for each integration", () => {
    expect(toggleLabel("slack", true)).toBe("Turn alerts off");
    expect(toggleLabel("salesforce", false)).toBe("Turn syncing on");
  });
});

describe("installNotice", () => {
  it("reads what Slack sent back", () => {
    expect(installNotice("cancelled")).toBe("Slack wasn't added.");
    expect(installNotice("connecting")).toMatch(/^Slack sent you back/);
    expect(installNotice(undefined)).toBeNull();
  });
});
