"""decisioning: risk scores and decisions, scored from the lead timeline

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-07

P3-01 (ADR-013, ADR-045). `risk_scores` holds each lead's risk of falling through, with the
model version, the inputs it saw and its reasons; the worker writes them and owners read them.
`decisions` holds what an owner or staff member decided, as themselves, and which score they
saw. Both are append-only. A trigger on lead_events, owned by cornerpin_leads like the
integrations one (migration 0016), queues `decisioning.score_lead` when something that bears on
the score happens. Every open lead is queued once, so existing leads get a first score.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "tenant_id = (SELECT app_tenant_id())"
NEW_TABLES = ("risk_scores", "decisions")
SCORED_KINDS = (
    "'inquiry', 'hold_requested', 'hold_approved', 'hold_declined', 'hold_withdrawn',"
    " 'consent_changed', 'stage_changed', 'message_sent', 'message_received'"
)

TABLES = """
ALTER TABLE hold_requests ADD CONSTRAINT hold_requests_id_tenant_id_key UNIQUE (id, tenant_id);

CREATE TABLE risk_scores (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       uuid NOT NULL,
  lead_id         uuid NOT NULL,
  hold_request_id uuid,
  model_version   text NOT NULL,
  score           numeric(4, 3) NOT NULL CHECK (score BETWEEN 0 AND 1),
  inputs          jsonb NOT NULL,
  reasons         jsonb NOT NULL CHECK (jsonb_typeof(reasons) = 'array'),
  scored_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, tenant_id),
  FOREIGN KEY (lead_id, tenant_id) REFERENCES leads (id, tenant_id) ON DELETE CASCADE,
  FOREIGN KEY (hold_request_id, tenant_id) REFERENCES hold_requests (id, tenant_id)
    ON DELETE CASCADE
);
CREATE INDEX risk_scores_lead_id_idx ON risk_scores (lead_id, scored_at DESC);
CREATE INDEX risk_scores_tenant_id_idx ON risk_scores (tenant_id, scored_at);

CREATE TYPE decision_kind AS ENUM ('hold_approved', 'hold_declined', 'lead_won', 'lead_lost');

CREATE TABLE decisions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  lead_id          uuid NOT NULL,
  hold_request_id  uuid,
  kind             decision_kind NOT NULL,
  decided_by       uuid REFERENCES users ON DELETE SET NULL,
  decided_by_email citext NOT NULL,
  risk_score_id    uuid,
  note             text NOT NULL DEFAULT '',
  decided_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lead_id, tenant_id) REFERENCES leads (id, tenant_id) ON DELETE CASCADE,
  FOREIGN KEY (hold_request_id, tenant_id) REFERENCES hold_requests (id, tenant_id)
    ON DELETE CASCADE,
  FOREIGN KEY (risk_score_id, tenant_id) REFERENCES risk_scores (id, tenant_id),
  CHECK ((kind::text LIKE 'hold_%') = (hold_request_id IS NOT NULL))
);
CREATE INDEX decisions_lead_id_idx ON decisions (lead_id, decided_at);
CREATE INDEX decisions_tenant_id_idx ON decisions (tenant_id, decided_at);
"""

POLICIES = f"""
CREATE POLICY risk_scores_tenant_read ON risk_scores FOR SELECT TO cornerpin_user
  USING ({TENANT});
GRANT SELECT ON risk_scores TO cornerpin_user;

CREATE POLICY risk_scores_worker_read ON risk_scores FOR SELECT TO cornerpin_worker
  USING (true);
CREATE POLICY risk_scores_worker_insert ON risk_scores FOR INSERT TO cornerpin_worker
  WITH CHECK (true);
GRANT SELECT, INSERT ON risk_scores TO cornerpin_worker;

CREATE POLICY decisions_tenant_read ON decisions FOR SELECT TO cornerpin_user
  USING ({TENANT});
CREATE POLICY decisions_tenant_insert ON decisions FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT} AND decided_by = (SELECT app_user_id()));
GRANT SELECT, INSERT ON decisions TO cornerpin_user;

-- The lot's phase says whether it is released, one of the score's inputs.
CREATE POLICY phases_worker_read ON phases FOR SELECT TO cornerpin_worker USING (true);
GRANT SELECT ON phases TO cornerpin_worker;
"""

TRIGGER = f"""
CREATE POLICY outbox_leads_score ON outbox FOR INSERT TO cornerpin_leads
  WITH CHECK (event_type = 'decisioning.score_lead');

CREATE FUNCTION lead_events_queue_score() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    BEGIN
      INSERT INTO outbox (event_type, payload)
      VALUES ('decisioning.score_lead', jsonb_build_object('lead_id', NEW.lead_id));
      RETURN NULL;
    END
  $$;
CREATE TRIGGER lead_events_score AFTER INSERT ON lead_events
  FOR EACH ROW WHEN (NEW.kind::text IN ({SCORED_KINDS}))
  EXECUTE FUNCTION lead_events_queue_score();

GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT CREATE ON SCHEMA public TO cornerpin_leads;
ALTER FUNCTION lead_events_queue_score() OWNER TO cornerpin_leads;
REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
REVOKE cornerpin_leads FROM CURRENT_USER;
"""  # noqa: S608 -- fixed SQL

# Each open lead once, so leads from before this migration get a first score. Held for ten
# minutes: a deploy migrates before the new API revision serves, and the old one has no handler
# for these, so it would spend their retries.
BACKFILL = """
INSERT INTO outbox (event_type, payload, available_at)
SELECT 'decisioning.score_lead', jsonb_build_object('lead_id', id), now() + interval '10 minutes'
FROM leads WHERE stage NOT IN ('won', 'lost') ORDER BY created_at;
"""


def upgrade() -> None:
    op.execute(TABLES)
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(POLICIES)
    op.execute(TRIGGER)
    # The migration's role is not exempt from RLS on Neon (tests/test_ops.py), so the backfill
    # lifts FORCE on the two tables it touches, as migration 0011 does.
    for table in ("leads", "outbox"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(BACKFILL)
    for table in ("leads", "outbox"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER lead_events_score ON lead_events;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION lead_events_queue_score();
        REVOKE cornerpin_leads FROM CURRENT_USER;
        DROP POLICY outbox_leads_score ON outbox;

        REVOKE SELECT ON phases FROM cornerpin_worker;
        DROP POLICY phases_worker_read ON phases;

        DROP TABLE decisions;
        DROP TYPE decision_kind;
        DROP TABLE risk_scores;
        ALTER TABLE hold_requests DROP CONSTRAINT hold_requests_id_tenant_id_key;
        """
    )
