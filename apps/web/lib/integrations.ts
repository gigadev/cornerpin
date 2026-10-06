import type { components } from "@/lib/api/schema";

// Integrations in the owner portal (P2-07, ADR-040): what a connection's state means to an owner.

export type Integration = components["schemas"]["Integration"];

/** One line on where the connection stands. */
export function slackSummary(slack: Integration): string {
  switch (slack.status) {
    case "connected": {
      // Ends on the workspace's own name, which may end in a full stop ("Co.").
      const where = [slack.channel, slack.workspace && `in ${slack.workspace}`]
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
      return slack.available
        ? "Not connected."
        : "Slack isn't set up on this Cornerpin yet.";
  }
}

/** What came back from Slack's install page, from the ?slack= query. */
export function installNotice(value: string | undefined): string | null {
  if (value === "connecting") return "Slack sent you back. Finishing the connection…";
  if (value === "cancelled") return "Slack wasn't added.";
  return null;
}
