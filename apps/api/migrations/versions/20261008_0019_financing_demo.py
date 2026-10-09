"""financing demo: applications, decisions, loans, schedules and payments; application scores

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08

P3-05 (ADR-013, ADR-049). Owner financing exists only on a demo tenant, on synthetic data:
`tenants.financing_demo` switches it on and may only be set on a demo tenant. Owners and staff
read their tenant's financing rows; writing them comes with P3-06 (the seed writes as the
owner). A financing application is scored like a lead, through the outbox: a trigger owned by
cornerpin_leads, as in migration 0018, queues `decisioning.score_application`, and its scores
sit in risk_scores beside the leads', with no lead.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "tenant_id = (SELECT app_tenant_id())"
NEW_TABLES = (
    "financing_applications",
    "financing_decisions",
    "loans",
    "loan_schedules",
    "loan_payments",
)

TABLES = """
ALTER TABLE tenants ADD COLUMN financing_demo boolean NOT NULL DEFAULT false,
  ADD CONSTRAINT tenants_financing_demo_only CHECK (NOT financing_demo OR is_demo);

CREATE TYPE financing_status AS ENUM ('submitted', 'approved', 'declined', 'withdrawn');
CREATE TYPE income_band AS ENUM ('under_50k', '50k_100k', '100k_150k', 'over_150k');
CREATE TYPE financing_decision_kind AS ENUM ('approved', 'declined');

CREATE TABLE financing_applications (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL,
  lot_id         uuid NOT NULL,
  user_id        uuid REFERENCES users ON DELETE SET NULL,
  applicant_name text NOT NULL,
  applicant_email citext NOT NULL,
  amount         numeric(12, 2) NOT NULL CHECK (amount > 0),
  down_payment   numeric(12, 2) NOT NULL CHECK (down_payment >= 0),
  term_months    integer NOT NULL CHECK (term_months IN (60, 120, 180, 240, 360)),
  income_band    income_band NOT NULL,
  status         financing_status NOT NULL DEFAULT 'submitted',
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, tenant_id),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE RESTRICT
);
CREATE INDEX financing_applications_tenant_idx ON financing_applications (tenant_id, created_at);

-- Who decided, and the score they saw. decided_by_email is NULL only on the synthetic seed's.
CREATE TABLE financing_decisions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  application_id   uuid NOT NULL,
  kind             financing_decision_kind NOT NULL,
  reason           text NOT NULL,
  decided_by       uuid REFERENCES users ON DELETE SET NULL,
  decided_by_email citext,
  risk_score_id    uuid,
  decided_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (application_id, tenant_id) REFERENCES financing_applications (id, tenant_id)
    ON DELETE CASCADE
);
CREATE INDEX financing_decisions_application_idx ON financing_decisions (application_id);

CREATE TABLE loans (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL,
  application_id uuid NOT NULL UNIQUE,
  principal      numeric(12, 2) NOT NULL CHECK (principal > 0),
  annual_rate    numeric(6, 4) NOT NULL CHECK (annual_rate >= 0 AND annual_rate < 1),
  term_months    integer NOT NULL CHECK (term_months > 0),
  first_due_on   date NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, tenant_id),
  FOREIGN KEY (application_id, tenant_id) REFERENCES financing_applications (id, tenant_id)
    ON DELETE CASCADE
);
CREATE INDEX loans_tenant_idx ON loans (tenant_id);

CREATE TABLE loan_schedules (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  loan_id   uuid NOT NULL,
  number    integer NOT NULL CHECK (number > 0),
  due_on    date NOT NULL,
  payment   numeric(12, 2) NOT NULL CHECK (payment > 0),
  principal numeric(12, 2) NOT NULL CHECK (principal >= 0),
  interest  numeric(12, 2) NOT NULL CHECK (interest >= 0),
  balance   numeric(12, 2) NOT NULL CHECK (balance >= 0),
  UNIQUE (loan_id, number),
  CHECK (payment = principal + interest),
  FOREIGN KEY (loan_id, tenant_id) REFERENCES loans (id, tenant_id) ON DELETE CASCADE
);

-- recorded_by_email is NULL only on the synthetic seed's payments.
CREATE TABLE loan_payments (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  loan_id           uuid NOT NULL,
  paid_on           date NOT NULL,
  amount            numeric(12, 2) NOT NULL CHECK (amount > 0),
  recorded_by       uuid REFERENCES users ON DELETE SET NULL,
  recorded_by_email citext,
  created_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (loan_id, tenant_id) REFERENCES loans (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX loan_payments_loan_idx ON loan_payments (loan_id, paid_on);

-- An application's scores sit beside the leads', with no lead.
ALTER TABLE risk_scores ALTER COLUMN lead_id DROP NOT NULL,
  ADD COLUMN financing_application_id uuid,
  ADD FOREIGN KEY (financing_application_id, tenant_id)
    REFERENCES financing_applications (id, tenant_id) ON DELETE CASCADE,
  ADD CONSTRAINT risk_scores_one_subject
    CHECK ((lead_id IS NULL) <> (financing_application_id IS NULL));
CREATE INDEX risk_scores_application_idx ON risk_scores (financing_application_id, scored_at DESC);
"""

POLICIES = (
    "\n".join(
        f"CREATE POLICY {table}_tenant_read ON {table} FOR SELECT TO cornerpin_user"
        f" USING ({TENANT});\nGRANT SELECT ON {table} TO cornerpin_user;"
        for table in NEW_TABLES
    )
    + """
-- The worker reads an application and its lot to score it.
CREATE POLICY financing_applications_worker_read ON financing_applications FOR SELECT
  TO cornerpin_worker USING (true);
GRANT SELECT ON financing_applications TO cornerpin_worker;
"""
)

TRIGGER = """
CREATE POLICY outbox_leads_score_application ON outbox FOR INSERT TO cornerpin_leads
  WITH CHECK (event_type = 'decisioning.score_application');

CREATE FUNCTION financing_applications_queue_score() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
    BEGIN
      INSERT INTO outbox (event_type, payload)
      VALUES ('decisioning.score_application', jsonb_build_object('application_id', NEW.id));
      RETURN NULL;
    END
  $$;
CREATE TRIGGER financing_applications_score AFTER INSERT ON financing_applications
  FOR EACH ROW EXECUTE FUNCTION financing_applications_queue_score();

GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT CREATE ON SCHEMA public TO cornerpin_leads;
ALTER FUNCTION financing_applications_queue_score() OWNER TO cornerpin_leads;
REVOKE CREATE ON SCHEMA public FROM cornerpin_leads;
REVOKE cornerpin_leads FROM CURRENT_USER;
"""


def upgrade() -> None:
    op.execute(TABLES)
    for table in NEW_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(POLICIES)
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER financing_applications_score ON financing_applications;
        GRANT cornerpin_leads TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION financing_applications_queue_score();
        REVOKE cornerpin_leads FROM CURRENT_USER;
        DROP POLICY outbox_leads_score_application ON outbox;

        DELETE FROM risk_scores WHERE financing_application_id IS NOT NULL;
        DROP INDEX risk_scores_application_idx;
        ALTER TABLE risk_scores DROP CONSTRAINT risk_scores_one_subject,
          DROP COLUMN financing_application_id, ALTER COLUMN lead_id SET NOT NULL;

        DROP TABLE loan_payments;
        DROP TABLE loan_schedules;
        DROP TABLE loans;
        DROP TABLE financing_decisions;
        DROP TABLE financing_applications;
        DROP TYPE financing_decision_kind;
        DROP TYPE income_band;
        DROP TYPE financing_status;
        ALTER TABLE tenants DROP CONSTRAINT tenants_financing_demo_only,
          DROP COLUMN financing_demo;
        """
    )
