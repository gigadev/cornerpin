"""integrations: connection status and sealed credentials; lead activity queued for them

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-06

P2-07 (ADR-040). A tenant's connection to an integration carries its status and, sealed with
the app's integrations key, the credentials it was given (Slack's webhook URL). Owners and staff
connect, toggle and remove connections, but can never read a secret back: they get column
grants without it. The worker completes connections and delivers to them.

A new lead's inquiry, a hold request and a handoff queue `integrations.lead_activity`, by
trigger, only for a tenant with a connected, enabled integration: a tenant without one never
gets the event.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNER_COLUMNS = "id, tenant_id, provider, enabled, settings, status, error, created_at, updated_at"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE integration_connections
          ADD COLUMN status text NOT NULL DEFAULT 'connecting'
            CHECK (status IN ('connecting', 'connected', 'failed')),
          ADD COLUMN error text,
          ADD COLUMN secret bytea;
        CREATE INDEX integration_connections_slack_team_idx
          ON integration_connections ((settings->>'team_id')) WHERE provider = 'slack';

        -- Owners never read a secret back.
        REVOKE SELECT, INSERT, UPDATE ON integration_connections FROM cornerpin_user;
        GRANT SELECT ({OWNER_COLUMNS}) ON integration_connections TO cornerpin_user;
        GRANT INSERT (tenant_id, provider, enabled, settings, status, error)
          ON integration_connections TO cornerpin_user;
        GRANT UPDATE (enabled, status, error) ON integration_connections TO cornerpin_user;

        CREATE POLICY integration_connections_worker ON integration_connections FOR ALL
          TO cornerpin_worker USING (true) WITH CHECK (true);
        GRANT SELECT, INSERT, UPDATE ON integration_connections TO cornerpin_worker;

        CREATE POLICY integration_connections_leads_read ON integration_connections FOR SELECT
          TO cornerpin_leads USING (true);
        GRANT SELECT (tenant_id, enabled, status) ON integration_connections TO cornerpin_leads;
        CREATE POLICY outbox_leads_enqueue ON outbox FOR INSERT TO cornerpin_leads
          WITH CHECK (event_type = 'integrations.lead_activity');
        GRANT INSERT ON outbox TO cornerpin_leads;

        CREATE FUNCTION lead_events_queue_integrations() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              IF EXISTS (SELECT FROM integration_connections c
                         WHERE c.tenant_id = NEW.tenant_id AND c.enabled
                           AND c.status = 'connected') THEN
                INSERT INTO outbox (event_type, payload)
                VALUES ('integrations.lead_activity',
                        jsonb_build_object('lead_event_id', NEW.id));
              END IF;
              RETURN NULL;
            END
          $$;
        CREATE TRIGGER lead_events_integrations AFTER INSERT ON lead_events
          FOR EACH ROW WHEN (NEW.kind::text IN ('inquiry', 'hold_requested', 'handoff'))
          EXECUTE FUNCTION lead_events_queue_integrations();

        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
        GRANT CREATE ON SCHEMA public TO cornerpin_leads;
        ALTER FUNCTION lead_events_queue_integrations() OWNER TO cornerpin_leads;
        REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
        REVOKE cornerpin_leads FROM CURRENT_USER;
        """  # noqa: S608 -- a fixed column list
    )


def downgrade() -> None:
    op.execute(
        f"""
        DROP TRIGGER lead_events_integrations ON lead_events;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION lead_events_queue_integrations();
        REVOKE cornerpin_leads FROM CURRENT_USER;

        REVOKE INSERT ON outbox FROM cornerpin_leads;
        DROP POLICY outbox_leads_enqueue ON outbox;
        REVOKE SELECT ON integration_connections FROM cornerpin_leads;
        DROP POLICY integration_connections_leads_read ON integration_connections;
        REVOKE SELECT, INSERT, UPDATE ON integration_connections FROM cornerpin_worker;
        DROP POLICY integration_connections_worker ON integration_connections;

        REVOKE SELECT ({OWNER_COLUMNS}), INSERT, UPDATE ON integration_connections
          FROM cornerpin_user;
        GRANT SELECT, INSERT, UPDATE ON integration_connections TO cornerpin_user;

        DROP INDEX integration_connections_slack_team_idx;
        ALTER TABLE integration_connections DROP COLUMN secret, DROP COLUMN error,
          DROP COLUMN status;
        """  # noqa: S608 -- a fixed column list
    )
