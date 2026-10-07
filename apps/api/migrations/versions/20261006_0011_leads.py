"""leads: one lead per buyer per tenant, with a timeline; outreach messages; integrations

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06

ADR-035. A buyer's activity with an owner (inquiries, hold requests and their decisions,
consent changes) becomes a lead and its timeline. Triggers write them in the same transaction
as the activity, so no code path can skip them. The activity is written as the buyer, or as
cornerpin_public for an anonymous inquiry, and neither may touch an owner's leads, so the
triggers run as cornerpin_leads: a role that can only maintain leads and their events.

Existing inquiries, hold requests and consents are replayed into leads in time order.

`outreach_messages` (P2-03) and `integration_connections` (P2-07, P2-08) are created here with
their tenant read policies; the tasks that write them add their writers.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "tenant_id = (SELECT app_tenant_id())"
NEW_TABLES = ("leads", "lead_events", "outreach_messages", "integration_connections")
# Read by the backfill, which runs as the migration's role: the tables' owner, which forced
# RLS would otherwise hold to policies it has none of.
SOURCE_TABLES = ("inquiries", "hold_requests", "contact_consents", "users")
RECORDERS = (
    "lead_touch(uuid, uuid, citext, text, text, text, timestamptz)",
    "lead_record_inquiry(inquiries)",
    "lead_record_hold(hold_requests)",
    "lead_record_hold_decision(hold_requests)",
    "lead_record_consent(contact_consents)",
)
TRIGGER_FUNCTIONS = (
    "leads_on_inquiry()",
    "leads_on_hold_request()",
    "leads_on_hold_decision()",
    "leads_on_consent()",
    "leads_on_stage_change()",
)

ROLE = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_leads') THEN
    CREATE ROLE cornerpin_leads NOLOGIN;
  END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO cornerpin_leads;
"""

TABLES = """
CREATE TYPE lead_stage AS ENUM ('new', 'contacted', 'engaged', 'holding', 'won', 'lost');
CREATE TYPE lead_event_kind AS ENUM (
  'inquiry', 'hold_requested', 'hold_approved', 'hold_declined', 'hold_withdrawn',
  'consent_changed', 'stage_changed', 'note'
);
CREATE TYPE outreach_direction AS ENUM ('outbound', 'inbound');
CREATE TYPE outreach_status AS ENUM ('queued', 'sent', 'refused', 'failed', 'received');
CREATE TYPE integration_provider AS ENUM ('slack', 'salesforce');

-- One per buyer per tenant. The email is the key: a signed-in buyer's verified address, or
-- what an anonymous inquiry typed. user_id is set only by a signed-in action.
CREATE TABLE leads (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  user_id          uuid REFERENCES users ON DELETE SET NULL,
  email            citext NOT NULL,
  name             text NOT NULL DEFAULT '',
  phone            text CHECK (phone ~ '^\\+[1-9][0-9]{6,14}$'),
  stage            lead_stage NOT NULL DEFAULT 'new',
  source           text NOT NULL,
  last_activity_at timestamptz NOT NULL DEFAULT now(),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email),
  UNIQUE (id, tenant_id)
);
CREATE UNIQUE INDEX leads_tenant_user_key ON leads (tenant_id, user_id) WHERE user_id IS NOT NULL;
CREATE INDEX leads_tenant_activity_idx ON leads (tenant_id, last_activity_at DESC);
CREATE TRIGGER leads_updated_at BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- The timeline. Append-only: nobody may update or delete an event. `verified` is false only
-- for an anonymous inquiry, whose email nobody has proved.
CREATE TABLE lead_events (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  lead_id         uuid NOT NULL,
  kind            lead_event_kind NOT NULL,
  lot_id          uuid,
  inquiry_id      uuid REFERENCES inquiries ON DELETE SET NULL,
  hold_request_id uuid REFERENCES hold_requests ON DELETE SET NULL,
  actor_user_id   uuid REFERENCES users ON DELETE SET NULL,
  verified        boolean NOT NULL DEFAULT true,
  detail          jsonb NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lead_id, tenant_id) REFERENCES leads (id, tenant_id) ON DELETE CASCADE,
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE SET NULL (lot_id)
);
CREATE INDEX lead_events_lead_idx ON lead_events (lead_id, created_at);

CREATE TABLE outreach_messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id           uuid NOT NULL,
  lead_id             uuid NOT NULL,
  channel             contact_channel NOT NULL,
  direction           outreach_direction NOT NULL,
  status              outreach_status NOT NULL,
  refused_reason      text,
  subject             text,
  body                text NOT NULL,
  provider            text,
  provider_message_id text,
  error               text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  sent_at             timestamptz,
  FOREIGN KEY (lead_id, tenant_id) REFERENCES leads (id, tenant_id) ON DELETE CASCADE,
  UNIQUE (provider, provider_message_id),
  CHECK ((status = 'refused') = (refused_reason IS NOT NULL))
);
CREATE INDEX outreach_messages_lead_idx ON outreach_messages (lead_id, created_at);

-- Per-tenant settings for an integration. Never credentials: where those live is decided in
-- P2-07.
CREATE TABLE integration_connections (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  provider   integration_provider NOT NULL,
  enabled    boolean NOT NULL DEFAULT false,
  settings   jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider)
);
CREATE TRIGGER integration_connections_updated_at BEFORE UPDATE ON integration_connections
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
"""

# The recorders take a source row, so the triggers and the backfill share them. Each runs as
# its owner, cornerpin_leads, set at the end of the migration.
RECORDER_FUNCTIONS = """
-- The buyer's lead with this owner, created or touched. A signed-in buyer's lead is keyed by
-- their verified address and gains their user id; an anonymous inquiry joins the lead for the
-- address it typed but never attaches a user.
CREATE FUNCTION lead_touch(
  tenant uuid, buyer uuid, typed_email citext, buyer_name text, buyer_phone text,
  first_source text, at timestamptz
) RETURNS uuid
  LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    INSERT INTO leads AS l (tenant_id, user_id, email, name, phone, source, created_at,
                            last_activity_at)
    SELECT tenant, buyer,
           CASE WHEN buyer IS NULL THEN typed_email
                ELSE (SELECT email FROM users WHERE id = buyer) END,
           coalesce(buyer_name, ''), buyer_phone, first_source, at, at
    ON CONFLICT (tenant_id, email) DO UPDATE SET
      user_id = coalesce(l.user_id, EXCLUDED.user_id),
      name = CASE WHEN l.name = '' THEN EXCLUDED.name ELSE l.name END,
      phone = coalesce(l.phone, EXCLUDED.phone),
      last_activity_at = greatest(l.last_activity_at, EXCLUDED.last_activity_at)
    RETURNING id
  $$;

CREATE FUNCTION lead_record_inquiry(i inquiries) RETURNS void
  LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    INSERT INTO lead_events (tenant_id, lead_id, kind, lot_id, inquiry_id, actor_user_id,
                             verified, detail, created_at)
    VALUES (i.tenant_id,
            lead_touch(i.tenant_id, i.user_id, i.email, i.name, i.phone, 'inquiry',
                       i.created_at),
            'inquiry', i.lot_id, i.id, i.user_id, i.user_id IS NOT NULL,
            jsonb_build_object('message', i.message), i.created_at)
  $$;

CREATE FUNCTION lead_record_hold(h hold_requests) RETURNS void
  LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    INSERT INTO lead_events (tenant_id, lead_id, kind, lot_id, hold_request_id, actor_user_id,
                             detail, created_at)
    VALUES (h.tenant_id,
            lead_touch(h.tenant_id, h.user_id, h.email, h.name, h.phone, 'hold_request',
                       h.created_at),
            'hold_requested', h.lot_id, h.id, h.user_id,
            jsonb_build_object('message', h.message), h.created_at)
  $$;

-- An approved hold moves the lead to "holding", unless it's already won or lost.
CREATE FUNCTION lead_record_hold_decision(h hold_requests) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    DECLARE
      lead uuid := lead_touch(h.tenant_id, h.user_id, h.email, h.name, h.phone, 'hold_request',
                              coalesce(h.decided_at, now()));
    BEGIN
      INSERT INTO lead_events (tenant_id, lead_id, kind, lot_id, hold_request_id, actor_user_id,
                               created_at)
      VALUES (h.tenant_id, lead, CAST('hold_' || h.status AS lead_event_kind), h.lot_id, h.id,
              CASE WHEN h.status = 'withdrawn' THEN h.user_id ELSE h.decided_by END,
              coalesce(h.decided_at, now()));
      IF h.status = 'approved' THEN
        UPDATE leads SET stage = 'holding'
        WHERE id = lead AND stage NOT IN ('holding', 'won', 'lost');
      END IF;
    END
  $$;

CREATE FUNCTION lead_record_consent(c contact_consents) RETURNS void
  LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id, detail, created_at)
    SELECT c.tenant_id,
           lead_touch(c.tenant_id, c.user_id, NULL, u.display_name, u.phone, c.source,
                      c.recorded_at),
           'consent_changed', c.user_id,
           jsonb_build_object('channel', c.channel, 'granted', c.granted, 'source', c.source),
           c.recorded_at
    FROM users u WHERE u.id = c.user_id
  $$;
"""

TRIGGERS = """
CREATE FUNCTION leads_on_inquiry() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ BEGIN PERFORM lead_record_inquiry(NEW); RETURN NULL; END $$;
CREATE FUNCTION leads_on_hold_request() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ BEGIN PERFORM lead_record_hold(NEW); RETURN NULL; END $$;
CREATE FUNCTION leads_on_hold_decision() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ BEGIN PERFORM lead_record_hold_decision(NEW); RETURN NULL; END $$;
CREATE FUNCTION leads_on_consent() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ BEGIN PERFORM lead_record_consent(NEW); RETURN NULL; END $$;
-- Every stage change is on the timeline, whether an owner or the system made it.
CREATE FUNCTION leads_on_stage_change() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    BEGIN
      INSERT INTO lead_events (tenant_id, lead_id, kind, actor_user_id, detail)
      VALUES (NEW.tenant_id, NEW.id, 'stage_changed', app_user_id(),
              jsonb_build_object('from', OLD.stage, 'to', NEW.stage));
      RETURN NULL;
    END
  $$;

CREATE TRIGGER inquiries_lead AFTER INSERT ON inquiries
  FOR EACH ROW EXECUTE FUNCTION leads_on_inquiry();
CREATE TRIGGER hold_requests_lead AFTER INSERT ON hold_requests
  FOR EACH ROW EXECUTE FUNCTION leads_on_hold_request();
CREATE TRIGGER hold_requests_lead_decision AFTER UPDATE OF status ON hold_requests
  FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status <> 'pending')
  EXECUTE FUNCTION leads_on_hold_decision();
CREATE TRIGGER contact_consents_lead AFTER INSERT ON contact_consents
  FOR EACH ROW EXECUTE FUNCTION leads_on_consent();
CREATE TRIGGER leads_stage_history AFTER UPDATE OF stage ON leads
  FOR EACH ROW WHEN (OLD.stage IS DISTINCT FROM NEW.stage)
  EXECUTE FUNCTION leads_on_stage_change();
"""

# Replays existing activity in time order, so each lead's source is its first touch. Runs before
# the new tables are forced, as their owner.
BACKFILL = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT 1 AS step, id, created_at AS at FROM inquiries
    UNION ALL SELECT 2, id, created_at FROM hold_requests
    UNION ALL SELECT 3, id, coalesce(decided_at, created_at) FROM hold_requests
      WHERE status <> 'pending'
    UNION ALL SELECT 4, id, recorded_at FROM contact_consents
    ORDER BY at, step
  LOOP
    CASE r.step
      WHEN 1 THEN PERFORM lead_record_inquiry(i) FROM inquiries i WHERE i.id = r.id;
      WHEN 2 THEN PERFORM lead_record_hold(h) FROM hold_requests h WHERE h.id = r.id;
      WHEN 3 THEN PERFORM lead_record_hold_decision(h) FROM hold_requests h WHERE h.id = r.id;
      ELSE PERFORM lead_record_consent(c) FROM contact_consents c WHERE c.id = r.id;
    END CASE;
  END LOOP;
END
$$;
"""

POLICIES = f"""
-- Owners and staff of the tenant read everything; they change a lead's stage and add notes.
CREATE POLICY leads_tenant_read ON leads FOR SELECT TO cornerpin_user USING ({TENANT});
CREATE POLICY leads_tenant_update ON leads FOR UPDATE TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY lead_events_tenant_read ON lead_events FOR SELECT TO cornerpin_user
  USING ({TENANT});
CREATE POLICY lead_events_tenant_note ON lead_events FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT} AND kind = 'note' AND actor_user_id = (SELECT app_user_id()));
CREATE POLICY outreach_messages_tenant_read ON outreach_messages FOR SELECT TO cornerpin_user
  USING ({TENANT});
CREATE POLICY integration_connections_tenant ON integration_connections FOR ALL
  TO cornerpin_user USING ({TENANT}) WITH CHECK ({TENANT});

-- The recorders.
CREATE POLICY leads_recorder ON leads FOR ALL TO cornerpin_leads
  USING (true) WITH CHECK (true);
CREATE POLICY lead_events_recorder ON lead_events FOR INSERT TO cornerpin_leads
  WITH CHECK (true);
CREATE POLICY users_leads_read ON users FOR SELECT TO cornerpin_leads USING (true);

GRANT SELECT, UPDATE (stage) ON leads TO cornerpin_user;
GRANT SELECT, INSERT ON lead_events TO cornerpin_user;
GRANT SELECT ON outreach_messages TO cornerpin_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON integration_connections TO cornerpin_user;
GRANT SELECT, INSERT, UPDATE ON leads TO cornerpin_leads;
GRANT INSERT ON lead_events TO cornerpin_leads;
GRANT SELECT (id, email, display_name, phone) ON users TO cornerpin_leads;
"""


def upgrade() -> None:
    op.execute(ROLE)
    op.execute(TABLES)
    op.execute(RECORDER_FUNCTIONS)
    for table in SOURCE_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(BACKFILL)
    for table in SOURCE_TABLES:
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(TRIGGERS)
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(POLICIES)
    # Only the triggers call the recorders. Revoked while this role still owns them.
    for function in RECORDERS:
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
    # Hand the functions to cornerpin_leads, as migration 0007 does for app_lot_is_public:
    # that takes SET ROLE on it, and its CREATE on the schema, both only for the hand-over.
    owned = "; ".join(
        f"ALTER FUNCTION {function} OWNER TO cornerpin_leads"
        for function in (*RECORDERS, *TRIGGER_FUNCTIONS)
    )
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
    op.execute(
        """
        DROP TRIGGER leads_stage_history ON leads;
        DROP TRIGGER contact_consents_lead ON contact_consents;
        DROP TRIGGER hold_requests_lead_decision ON hold_requests;
        DROP TRIGGER hold_requests_lead ON hold_requests;
        DROP TRIGGER inquiries_lead ON inquiries;
        DROP POLICY users_leads_read ON users;
        """
    )
    # Dropping cornerpin_leads' functions takes its privileges, briefly.
    drops = "; ".join(f"DROP FUNCTION {f}" for f in (*TRIGGER_FUNCTIONS, *RECORDERS))
    op.execute(
        f"""
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        {drops};
        REVOKE cornerpin_leads FROM CURRENT_USER;
        """
    )
    op.execute(
        """
        DROP TABLE integration_connections, outreach_messages, lead_events, leads;
        DROP TYPE integration_provider, outreach_status, outreach_direction, lead_event_kind,
          lead_stage;
        REVOKE USAGE ON SCHEMA public FROM cornerpin_leads;
        """
    )
