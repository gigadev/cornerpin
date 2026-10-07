"""outreach replies: inbound messages on the timeline; a reply makes a lead engaged

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06

P2-04 (ADR-037). A buyer's reply is an inbound outreach_messages row, written by the worker.
A trigger, as cornerpin_leads, puts it on the lead's timeline (verified only when it came from
the lead's own address) and marks the lead active. The worker may move a lead's stage, which
the stage trigger records like any other change.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'message_received'")
    op.execute(
        """
        ALTER TABLE outreach_messages ADD COLUMN from_address citext;

        CREATE FUNCTION outreach_on_inbound() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              INSERT INTO lead_events (tenant_id, lead_id, kind, verified, detail)
              SELECT NEW.tenant_id, NEW.lead_id, 'message_received'::lead_event_kind,
                     NEW.from_address IS NOT DISTINCT FROM l.email,
                     jsonb_strip_nulls(jsonb_build_object(
                       'message_id', NEW.id, 'channel', NEW.channel, 'subject', NEW.subject,
                       'message', left(NEW.body, 2000)))
              FROM leads l WHERE l.id = NEW.lead_id;
              UPDATE leads SET last_activity_at = greatest(last_activity_at, NEW.created_at)
              WHERE id = NEW.lead_id;
              RETURN NULL;
            END
          $$;
        CREATE TRIGGER outreach_messages_inbound AFTER INSERT ON outreach_messages
          FOR EACH ROW WHEN (NEW.direction = 'inbound')
          EXECUTE FUNCTION outreach_on_inbound();

        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
        GRANT CREATE ON SCHEMA public TO cornerpin_leads;
        ALTER FUNCTION outreach_on_inbound() OWNER TO cornerpin_leads;
        REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
        REVOKE cornerpin_leads FROM CURRENT_USER;

        CREATE POLICY leads_worker_stage ON leads FOR UPDATE TO cornerpin_worker
          USING (true) WITH CHECK (true);
        GRANT UPDATE (stage) ON leads TO cornerpin_worker;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE UPDATE (stage) ON leads FROM cornerpin_worker;
        DROP POLICY leads_worker_stage ON leads;
        DROP TRIGGER outreach_messages_inbound ON outreach_messages;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION outreach_on_inbound();
        REVOKE cornerpin_leads FROM CURRENT_USER;
        ALTER TABLE outreach_messages DROP COLUMN from_address;
        """
    )
    # Postgres can't drop enum values; 'message_received' stays, unused.
