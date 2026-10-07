"""lead handoffs and event authors

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-06

P2-02 (ADR-035). A lead that needs a person carries `handoff_at` and a reason until an owner
marks it handled; both are timeline events, written by trigger with who did it. The outreach
agent sets the handoff in P2-05.

Timeline events keep the email of whoever acted, as lot history does (migration 0004): owners
can't read other users, and the name must survive the account's removal.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCTIONS = ("leads_on_handoff()", "lead_events_actor_email()")


def upgrade() -> None:
    # New enum values can't be used in the transaction that adds them; the functions below only
    # name them in plpgsql bodies, which are checked when they run.
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'handoff'")
    op.execute("ALTER TYPE lead_event_kind ADD VALUE IF NOT EXISTS 'handoff_resolved'")
    op.execute(
        """
        ALTER TABLE leads ADD COLUMN handoff_at timestamptz;
        ALTER TABLE leads ADD COLUMN handoff_reason text;
        ALTER TABLE leads ADD CONSTRAINT leads_handoff_reason
          CHECK (handoff_at IS NOT NULL OR handoff_reason IS NULL);
        CREATE INDEX leads_handoff_idx ON leads (tenant_id, handoff_at)
          WHERE handoff_at IS NOT NULL;
        ALTER TABLE lead_events ADD COLUMN actor_email citext;

        CREATE FUNCTION leads_on_handoff() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              IF NEW.handoff_at IS NOT NULL AND OLD.handoff_at IS NULL THEN
                INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id, detail)
                VALUES (NEW.tenant_id, NEW.id, 'handoff', app_user_id(),
                        jsonb_build_object('reason', coalesce(NEW.handoff_reason, '')));
              ELSIF NEW.handoff_at IS NULL AND OLD.handoff_at IS NOT NULL THEN
                INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id)
                VALUES (NEW.tenant_id, NEW.id, 'handoff_resolved', app_user_id());
              END IF;
              RETURN NULL;
            END
          $$;
        CREATE TRIGGER leads_handoff_history AFTER UPDATE OF handoff_at ON leads
          FOR EACH ROW WHEN (OLD.handoff_at IS DISTINCT FROM NEW.handoff_at)
          EXECUTE FUNCTION leads_on_handoff();

        CREATE FUNCTION lead_events_actor_email() RETURNS trigger
          LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
          AS $$
            BEGIN
              NEW.actor_email := (SELECT email FROM users WHERE id = NEW.actor_user_id);
              RETURN NEW;
            END
          $$;
        CREATE TRIGGER lead_events_actor BEFORE INSERT ON lead_events
          FOR EACH ROW EXECUTE FUNCTION lead_events_actor_email();

        -- Owners mark a handoff handled; only the handoff columns and the stage are theirs.
        GRANT UPDATE (handoff_at, handoff_reason) ON leads TO cornerpin_user;
        """
    )
    # Events from 0011 get their authors. The table's owner is held to policies while RLS is
    # forced, and there are none for it, so lift it for this one update.
    op.execute(
        """
        ALTER TABLE lead_events NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE users NO FORCE ROW LEVEL SECURITY;
        UPDATE lead_events e SET actor_email = u.email FROM users u WHERE u.id = e.actor_user_id;
        ALTER TABLE lead_events FORCE ROW LEVEL SECURITY;
        ALTER TABLE users FORCE ROW LEVEL SECURITY;
        """
    )
    owned = "; ".join(f"ALTER FUNCTION {f} OWNER TO cornerpin_leads" for f in FUNCTIONS)
    op.execute(
        f"""
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
        GRANT CREATE ON SCHEMA public TO cornerpin_leads;
        {owned};
        REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
        REVOKE cornerpin_leads FROM CURRENT_USER;
        """
    )


def downgrade() -> None:
    drops = "; ".join(f"DROP FUNCTION {f}" for f in FUNCTIONS)
    op.execute(
        f"""
        DROP TRIGGER lead_events_actor ON lead_events;
        DROP TRIGGER leads_handoff_history ON leads;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        {drops};
        REVOKE cornerpin_leads FROM CURRENT_USER;
        REVOKE UPDATE (handoff_at, handoff_reason) ON leads FROM cornerpin_user;
        ALTER TABLE lead_events DROP COLUMN actor_email;
        DROP INDEX leads_handoff_idx;
        ALTER TABLE leads DROP CONSTRAINT leads_handoff_reason;
        ALTER TABLE leads DROP COLUMN handoff_reason;
        ALTER TABLE leads DROP COLUMN handoff_at;
        """
    )
    # Postgres can't drop enum values; 'handoff' and 'handoff_resolved' stay, unused.
