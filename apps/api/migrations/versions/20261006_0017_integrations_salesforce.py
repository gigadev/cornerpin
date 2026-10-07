"""integrations: Salesforce credentials from the portal; stage changes, approved holds and lots
queued for integrations

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-06

P2-08 (ADR-041). An owner types their org's Salesforce credentials into the portal, so the
portal role may now write a connection's sealed secret and settings; it still can't read the
secret back. Lead activity queued for integrations now includes stage changes and approved
holds (Salesforce tracks both; Slack ignores them), and a lot's changes queue
`integrations.lot_changed` for a tenant with Salesforce connected. Lots are changed as the
owner, so that trigger runs as its caller, like queue_lot_change (migration 0008).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_KINDS = "'inquiry', 'hold_requested', 'handoff'"
MORE_KINDS = ACTIVITY_KINDS + ", 'stage_changed', 'hold_approved'"


def _activity_trigger(kinds: str) -> str:
    return f"""
        DROP TRIGGER lead_events_integrations ON lead_events;
        CREATE TRIGGER lead_events_integrations AFTER INSERT ON lead_events
          FOR EACH ROW WHEN (NEW.kind::text IN ({kinds}))
          EXECUTE FUNCTION lead_events_queue_integrations();
    """


def upgrade() -> None:
    op.execute(
        """
        GRANT INSERT (secret), UPDATE (settings, secret) ON integration_connections
          TO cornerpin_user;

        CREATE FUNCTION lots_queue_integrations() RETURNS trigger
          LANGUAGE plpgsql
          AS $$
            BEGIN
              IF EXISTS (SELECT FROM integration_connections c
                         WHERE c.tenant_id = NEW.tenant_id AND c.provider = 'salesforce'
                           AND c.enabled AND c.status = 'connected') THEN
                INSERT INTO outbox (event_type, payload)
                VALUES ('integrations.lot_changed', jsonb_build_object('lot_id', NEW.id));
              END IF;
              RETURN NULL;
            END
          $$;
        CREATE TRIGGER lots_integrations AFTER INSERT OR UPDATE OF number, status, price,
          published, listing_type ON lots
          FOR EACH ROW EXECUTE FUNCTION lots_queue_integrations();
        """
    )
    op.execute(_activity_trigger(MORE_KINDS))


def downgrade() -> None:
    op.execute(_activity_trigger(ACTIVITY_KINDS))
    op.execute(
        """
        DROP TRIGGER lots_integrations ON lots;
        DROP FUNCTION lots_queue_integrations();
        REVOKE INSERT (secret), UPDATE (settings, secret) ON integration_connections
          FROM cornerpin_user;
        """
    )
