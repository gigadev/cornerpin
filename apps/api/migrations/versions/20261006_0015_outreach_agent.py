"""outreach agent: its tool calls on the timeline, its handoffs, and what it sent

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-06

P2-05 (ADR-038). The agent runs in outbox handlers, as cornerpin_worker. It may append its own
tool calls to a lead's timeline (kind agent_action, nothing else) and hand a lead to a person,
which the handoff trigger records. A sent message's event now carries its text, so the owner
reads what the agent wrote.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _on_outcome(detail: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION outreach_on_outcome() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              INSERT INTO lead_events (tenant_id, lead_id, kind, detail)
              VALUES (
                NEW.tenant_id, NEW.lead_id,
                CASE NEW.status WHEN 'sent' THEN 'message_sent' ELSE 'message_refused' END
                  ::lead_event_kind,
                jsonb_strip_nulls(jsonb_build_object({detail})));
              RETURN NULL;
            END
          $$;
    """  # noqa: S608 -- the detail is one of two fixed column lists


OUTCOME_BEFORE = (
    "'message_id', NEW.id, 'channel', NEW.channel, 'subject', NEW.subject,"
    " 'reason', NEW.refused_reason"
)
OUTCOME_AFTER = (
    OUTCOME_BEFORE + ", 'message', CASE NEW.status WHEN 'sent' THEN left(NEW.body, 4000) END"
)


def _replace_outcome(detail: str) -> str:
    # The function belongs to cornerpin_leads; replacing it takes that role, briefly.
    return f"""
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        {_on_outcome(detail)}
        REVOKE cornerpin_leads FROM CURRENT_USER;
    """


def upgrade() -> None:
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'agent_action'")
    # The new value can't be used as an enum in this transaction, so the policy compares text.
    op.execute(
        """
        CREATE POLICY lead_events_worker_agent ON lead_events FOR INSERT TO cornerpin_worker
          WITH CHECK (kind::text = 'agent_action' AND actor_user_id IS NULL);
        GRANT INSERT ON lead_events TO cornerpin_worker;

        ALTER POLICY leads_worker_stage ON leads RENAME TO leads_worker_update;
        GRANT UPDATE (handoff_at, handoff_reason) ON leads TO cornerpin_worker;
        """
    )
    op.execute(_replace_outcome(OUTCOME_AFTER))


def downgrade() -> None:
    op.execute(_replace_outcome(OUTCOME_BEFORE))
    op.execute(
        """
        REVOKE UPDATE (handoff_at, handoff_reason) ON leads FROM cornerpin_worker;
        ALTER POLICY leads_worker_update ON leads RENAME TO leads_worker_stage;
        REVOKE INSERT ON lead_events FROM cornerpin_worker;
        DROP POLICY lead_events_worker_agent ON lead_events;
        """
    )
    # Postgres can't drop enum values; 'agent_action' stays, unused.
