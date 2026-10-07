"""outreach sends: the worker sends and logs them; sends and refusals are on the timeline

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06

P2-03 (ADR-036). Outreach is sent only from outbox handlers, which run as cornerpin_worker. It
reads a lead, its consent and its lots to decide whether a message may go now, and writes the
message's row (queued, then sent, refused or failed). A message that is sent or refused becomes
a timeline event, written by trigger as cornerpin_leads.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_READS = ("leads", "lead_events", "contact_consents")
# /unsubscribe is a page now, so no subdivision may take that address (listings.schemas).
RESERVED = (
    "'app', 'q', 'api', 'v1', 'graphql', 'internal', 'serwist', 'icons', 'static', 'admin',"
    " 'auth', 'login', 'logout', 'signin', 'signup', 'account', 'settings', 'about', 'help',"
    " 'terms', 'privacy', 'offline'"
)


def _reserve(slugs: str) -> None:
    op.execute(
        "ALTER TABLE subdivisions DROP CONSTRAINT subdivisions_slug_check1;"
        f" ALTER TABLE subdivisions ADD CONSTRAINT subdivisions_slug_check1"
        f" CHECK (slug NOT IN ({slugs}))"
    )


def upgrade() -> None:
    _reserve(RESERVED + ", 'unsubscribe'")
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'message_sent'")
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'message_refused'")
    for table in WORKER_READS:
        op.execute(
            f"CREATE POLICY {table}_worker_read ON {table} FOR SELECT TO cornerpin_worker"
            f" USING (true); GRANT SELECT ON {table} TO cornerpin_worker"
        )
    op.execute(
        """
        CREATE POLICY outreach_messages_worker ON outreach_messages FOR ALL TO cornerpin_worker
          USING (true) WITH CHECK (true);
        GRANT SELECT, INSERT, UPDATE ON outreach_messages TO cornerpin_worker;
        CREATE INDEX outreach_messages_tenant_sent_idx ON outreach_messages (tenant_id, sent_at)
          WHERE status = 'sent';

        CREATE FUNCTION outreach_on_outcome() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              INSERT INTO lead_events (tenant_id, lead_id, kind, detail)
              VALUES (
                NEW.tenant_id, NEW.lead_id,
                CASE NEW.status WHEN 'sent' THEN 'message_sent' ELSE 'message_refused' END
                  ::lead_event_kind,
                jsonb_strip_nulls(jsonb_build_object(
                  'message_id', NEW.id, 'channel', NEW.channel, 'subject', NEW.subject,
                  'reason', NEW.refused_reason)));
              RETURN NULL;
            END
          $$;
        CREATE TRIGGER outreach_messages_outcome AFTER UPDATE OF status ON outreach_messages
          FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status
                             AND NEW.status IN ('sent', 'refused'))
          EXECUTE FUNCTION outreach_on_outcome();

        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
        GRANT CREATE ON SCHEMA public TO cornerpin_leads;
        ALTER FUNCTION outreach_on_outcome() OWNER TO cornerpin_leads;
        REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
        REVOKE cornerpin_leads FROM CURRENT_USER;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER outreach_messages_outcome ON outreach_messages;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION outreach_on_outcome();
        REVOKE cornerpin_leads FROM CURRENT_USER;
        DROP INDEX outreach_messages_tenant_sent_idx;
        REVOKE SELECT, INSERT, UPDATE ON outreach_messages FROM cornerpin_worker;
        DROP POLICY outreach_messages_worker ON outreach_messages;
        """
    )
    for table in WORKER_READS:
        op.execute(
            f"REVOKE SELECT ON {table} FROM cornerpin_worker;"  # noqa: S608 -- a fixed table list
            f" DROP POLICY {table}_worker_read ON {table}"
        )
    _reserve(RESERVED)
    # Postgres can't drop enum values; 'message_sent' and 'message_refused' stay, unused.
