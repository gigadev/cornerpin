import { describe, expect, it } from "vitest";
import { describeEvent, eventActor, isLeadStage, leadStageLabel, type LeadEvent } from "./leads";

const base: LeadEvent = {
  id: "e1",
  kind: "inquiry",
  created_at: "2026-10-06T16:00:00Z",
  by_buyer: true,
  verified: true,
  actor_email: "pat@example.test",
  lot: { lot_id: "l1", number: "2-5", subdivision_name: "Juniper Bench" },
  message: "Is the well shared?",
  note: null,
  channel: null,
  granted: null,
  consent_source: null,
  from_stage: null,
  to_stage: null,
  reason: null,
  subject: null,
  tool: null,
};

describe("describeEvent", () => {
  it("names the lot and keeps the buyer's words", () => {
    expect(describeEvent(base)).toEqual({
      title: "Asked about Lot 2-5, Juniper Bench",
      body: "Is the well shared?",
    });
    expect(describeEvent({ ...base, kind: "hold_requested", message: "" })).toEqual({
      title: "Asked to hold Lot 2-5, Juniper Bench",
      body: null,
    });
  });

  it("reads consent, stage changes, notes and handoffs", () => {
    const consent = { ...base, kind: "consent_changed", lot: null } as const;
    expect(describeEvent({ ...consent, channel: "sms", granted: true }).title).toBe(
      "Allowed text messages",
    );
    expect(describeEvent({ ...consent, channel: "email", granted: false }).title).toBe(
      "Stopped email",
    );
    expect(
      describeEvent({ ...base, kind: "stage_changed", from_stage: "new", to_stage: "won" }).title,
    ).toBe("Stage: New → Won");
    expect(describeEvent({ ...base, kind: "note", note: "Call back Friday" })).toEqual({
      title: "Note",
      body: "Call back Friday",
    });
    expect(describeEvent({ ...base, kind: "handoff", reason: "Asked about financing" })).toEqual({
      title: "Needs a person",
      body: "Asked about financing",
    });
  });
});

describe("outreach messages", () => {
  it("say what was sent, or why not", () => {
    const sent = {
      ...base,
      kind: "message_sent",
      by_buyer: false,
      lot: null,
      message: null,
    } as const;
    expect(describeEvent({ ...sent, channel: "email", subject: "Saturday?" })).toEqual({
      title: "Email sent",
      body: "Saturday?",
    });
    expect(
      describeEvent({ ...sent, kind: "message_refused", reason: "opted_out", subject: "Hi" }),
    ).toEqual({ title: "Not sent: they opted out", body: "Hi" });
    const reply = { ...sent, kind: "message_received", by_buyer: true, message: "Yes, 10?" };
    expect(describeEvent(reply as LeadEvent)).toEqual({ title: "Replied", body: "Yes, 10?" });
  });
});

describe("the assistant", () => {
  it("shows its tool calls, and the text of what it sent", () => {
    const action = { ...base, kind: "agent_action", by_buyer: false, message: null } as const;
    expect(describeEvent({ ...action, tool: "lookup_lot", note: "Available, $90,000" })).toEqual({
      title: "Assistant looked up Lot 2-5, Juniper Bench",
      body: "Available, $90,000",
    });
    expect(
      describeEvent({ ...action, tool: "check_availability", lot: null, note: "3 available" }),
    ).toEqual({ title: "Assistant checked what's available", body: "3 available" });
    expect(describeEvent({ ...action, tool: "log_timeline", note: "Budget $100k" }).title).toBe(
      "Assistant's note",
    );
    expect(eventActor({ ...action, tool: "log_timeline" }, "Pat")).toBe("Cornerpin assistant");

    const sent = { ...base, kind: "message_sent", by_buyer: false, lot: null } as const;
    expect(
      describeEvent({ ...sent, channel: "email", subject: "About Lot 1", message: "Hi Pat" }),
    ).toEqual({ title: "Email sent", body: "About Lot 1\n\nHi Pat" });
  });
});

describe("eventActor", () => {
  it("is the buyer for their own actions, flagged when the email isn't proven", () => {
    expect(eventActor(base, "Pat")).toBe("Pat");
    expect(eventActor({ ...base, verified: false, actor_email: null }, "Pat")).toBe(
      "Pat (email not verified)",
    );
  });

  it("is whoever was signed in otherwise, or the system", () => {
    const owner = { ...base, kind: "note", by_buyer: false, actor_email: "owner@x.test" } as const;
    expect(eventActor(owner, "Pat")).toBe("owner@x.test");
    expect(eventActor({ ...owner, actor_email: null }, "Pat")).toBe("Cornerpin");
  });
});

describe("stages", () => {
  it("labels and recognises them", () => {
    expect(leadStageLabel("holding")).toBe("Holding");
    expect(isLeadStage("won")).toBe(true);
    expect(isLeadStage("maybe")).toBe(false);
    expect(isLeadStage(undefined)).toBe(false);
  });
});
