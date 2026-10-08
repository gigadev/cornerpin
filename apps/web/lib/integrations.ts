import type { components } from "@/lib/api/schema";

// Integrations in the owner portal (P2-07, P2-08; ADR-040, ADR-041): what a connection's state
// means to an owner.

export type Integration = components["schemas"]["Integration"];
export type Provider = Integration["provider"];

/** One line on where Slack stands. */
export function slackSummary(slack: Integration): string {
  switch (slack.status) {
    case "connected": {
      // Ends on the workspace's own name, which may end in a full stop ("Co.").
      const where = [slack.channel, slack.account && `in ${slack.account}`]
        .filter(Boolean)
        .join(" ");
      const alerts = slack.enabled ? "Alerts on" : "Alerts off (/lot still answers)";
      return `Connected. ${alerts}${where ? `: ${where}` : "."}`;
    }
    case "connecting":
      return "Connecting to Slack. This takes a few seconds; refresh to check.";
    case "failed":
      return slack.error ?? "The connection stopped working. Add Slack again.";
    case "not_connected":
      return slack.available ? "Not connected." : "Slack isn't set up on this Cornerpin yet.";
  }
}

/** One line on where Salesforce stands. */
export function salesforceSummary(salesforce: Integration): string {
  switch (salesforce.status) {
    case "connected": {
      const sync = salesforce.enabled ? "Syncing" : "Syncing is off";
      return `Connected. ${sync}${salesforce.account ? `: ${salesforce.account}` : "."}`;
    }
    case "connecting":
      return "Connecting: signing in, setting up Cornerpin's fields and sending your lots. Refresh in a moment.";
    case "failed":
      return salesforce.error ?? "The connection stopped working. Enter the details again.";
    case "not_connected":
      return "Not connected.";
  }
}

/** The on/off button's words for each integration. */
export function toggleLabel(provider: Provider, enabled: boolean): string {
  const what = provider === "slack" ? "alerts" : "syncing";
  return enabled ? `Turn ${what} off` : `Turn ${what} on`;
}

/** What came back from Slack's install page, from the ?slack= query. The query stays in the
 * address after a refresh, so "connecting" shows only while Slack's status still says so. */
export function installNotice(
  value: string | undefined,
  status: Integration["status"] | undefined,
): string | null {
  if (value === "connecting") {
    return status === "connecting" ? "Slack sent you back. Finishing the connection…" : null;
  }
  if (value === "cancelled") return "Slack wasn't added.";
  return null;
}
