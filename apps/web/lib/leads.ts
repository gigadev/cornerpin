import type { components } from "@/lib/api/schema";
import { channelLabel } from "./format";

// Leads in the owner portal (P2-02, ADR-035): stage names and how timeline events read.

export type LeadStage = components["schemas"]["LeadSummary"]["stage"];
export type LeadEvent = components["schemas"]["LeadEvent"];

export const LEAD_STAGES = [
  "new",
  "contacted",
  "engaged",
  "holding",
  "won",
  "lost",
] as const satisfies readonly LeadStage[];

const STAGE_LABELS: Record<LeadStage, string> = {
  new: "New",
  contacted: "Contacted",
  engaged: "Engaged",
  holding: "Holding",
  won: "Won",
  lost: "Lost",
};

export function leadStageLabel(stage: LeadStage): string {
  return STAGE_LABELS[stage];
}

export function isLeadStage(value: string | undefined): value is LeadStage {
  return LEAD_STAGES.some((stage) => stage === value);
}

function lotName(event: LeadEvent): string {
  return event.lot ? `Lot ${event.lot.number}, ${event.lot.subdivision_name}` : "a lot";
}

/** What happened, in a line, and any text that came with it. */
export function describeEvent(event: LeadEvent): { title: string; body: string | null } {
  switch (event.kind) {
    case "inquiry":
      return { title: `Asked about ${lotName(event)}`, body: event.message ?? null };
    case "hold_requested":
      return { title: `Asked to hold ${lotName(event)}`, body: event.message || null };
    case "hold_approved":
      return { title: `Hold approved on ${lotName(event)}`, body: null };
    case "hold_declined":
      return { title: `Hold declined on ${lotName(event)}`, body: null };
    case "hold_withdrawn":
      return { title: `Hold withdrawn on ${lotName(event)}`, body: null };
    case "consent_changed": {
      const channel = event.channel ? channelLabel(event.channel).toLowerCase() : "contact";
      return {
        title: event.granted ? `Allowed ${channel}` : `Stopped ${channel}`,
        body: null,
      };
    }
    case "stage_changed":
      return {
        title:
          event.from_stage && event.to_stage
            ? `Stage: ${leadStageLabel(event.from_stage)} → ${leadStageLabel(event.to_stage)}`
            : "Stage changed",
        body: null,
      };
    case "note":
      return { title: "Note", body: event.note ?? null };
    case "handoff":
      return { title: "Needs a person", body: event.reason ?? null };
    case "handoff_resolved":
      return { title: "Marked handled", body: null };
    case "message_sent":
      return {
        title: `${event.channel ? channelLabel(event.channel) : "Message"} sent`,
        body: [event.subject, event.message].filter(Boolean).join("\n\n") || null,
      };
    case "message_received":
      return { title: "Replied", body: event.message ?? null };
    case "agent_action":
      return { title: agentTitle(event), body: event.note ?? null };
    case "message_refused": {
      const why = event.reason ? (REFUSALS[event.reason] ?? event.reason) : null;
      return { title: why ? `Not sent: ${why}` : "Not sent", body: event.subject ?? null };
    }
  }
}

// The outreach agent's tool calls (P2-05, ADR-038). Handoffs and tour requests show as the
// lead's handoff; these appear only when the lead was already with a person.
function agentTitle(event: LeadEvent): string {
  switch (event.tool) {
    case "lookup_lot":
      return `Assistant looked up ${event.lot ? lotName(event) : "a lot"}`;
    case "check_availability":
      return "Assistant checked what's available";
    case "log_timeline":
      return "Assistant's note";
    case "request_tour":
      return "Assistant passed on a tour request";
    case "handoff_to_human":
      return "Assistant asked for a person";
    default:
      return "Assistant";
  }
}

const REFUSALS: Record<string, string> = {
  no_consent: "they haven't allowed it",
  opted_out: "they opted out",
  lead_daily_cap: "daily limit for this person reached",
  tenant_daily_cap: "your organization's daily limit reached",
  channel_unavailable: "that channel isn't available yet",
};

/** Who did it: the buyer for their own actions, the assistant for its tool calls, else whoever
 * was signed in, else the system. */
export function eventActor(event: LeadEvent, leadName: string): string {
  if (event.kind === "agent_action") return "Cornerpin assistant";
  if (event.by_buyer) return event.verified ? leadName : `${leadName} (email not verified)`;
  return event.actor_email ?? "Cornerpin";
}
