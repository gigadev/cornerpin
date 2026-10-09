"""financing demo writes: buyers apply, owners decide, lend and record payments

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08

P3-06 (ADR-049, ADR-050). A signed-in buyer may apply only for a public lot of a tenant with
the financing demo on, one open application per lot, and reads their own applications and the
decisions on them. Owners and staff decide as themselves, create the loan and its schedule, and
record payments as themselves. A decision keeps the principal reasons the buyer was given, so
what they were told never depends on reading a score later.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "tenant_id = (SELECT app_tenant_id())"
SELF = "user_id = (SELECT app_user_id())"
ME = "(SELECT app_user_id())"

FUNCTION = """
CREATE FUNCTION app_tenant_offers_financing(tenant uuid) RETURNS boolean
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ SELECT coalesce((SELECT financing_demo FROM tenants WHERE id = tenant), false) $$;
-- Owned by the worker, which already reads tenants; it answers only yes or no for one tenant.
GRANT cornerpin_worker TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
GRANT CREATE ON SCHEMA public TO cornerpin_worker;
ALTER FUNCTION app_tenant_offers_financing(uuid) OWNER TO cornerpin_worker;
REVOKE CREATE ON SCHEMA public FROM cornerpin_worker;
REVOKE cornerpin_worker FROM CURRENT_USER;
REVOKE ALL ON FUNCTION app_tenant_offers_financing(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_tenant_offers_financing(uuid) TO cornerpin_user, cornerpin_public;
"""

POLICIES = f"""
ALTER TABLE financing_decisions
  ADD COLUMN principal_reasons jsonb NOT NULL DEFAULT '[]'
    CHECK (jsonb_typeof(principal_reasons) = 'array');
CREATE UNIQUE INDEX financing_applications_one_open_idx ON financing_applications (lot_id, user_id)
  WHERE status = 'submitted';

CREATE POLICY financing_applications_own_read ON financing_applications FOR SELECT
  TO cornerpin_user USING ({SELF});
CREATE POLICY financing_applications_apply ON financing_applications FOR INSERT
  TO cornerpin_user
  WITH CHECK ({SELF} AND app_lot_is_public(lot_id) AND app_tenant_offers_financing(tenant_id)
              AND status = 'submitted');
GRANT INSERT (id, tenant_id, lot_id, user_id, applicant_name, applicant_email, amount, down_payment,
              term_months, income_band) ON financing_applications TO cornerpin_user;
CREATE POLICY financing_applications_decide ON financing_applications FOR UPDATE
  TO cornerpin_user USING ({TENANT}) WITH CHECK ({TENANT});
GRANT UPDATE (status) ON financing_applications TO cornerpin_user;

CREATE POLICY financing_decisions_own_read ON financing_decisions FOR SELECT TO cornerpin_user
  USING (EXISTS (SELECT 1 FROM financing_applications a
                 WHERE a.id = application_id AND a.user_id = {ME}));
CREATE POLICY financing_decisions_decide ON financing_decisions FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT} AND decided_by = {ME});
GRANT INSERT ON financing_decisions TO cornerpin_user;

CREATE POLICY loans_lend ON loans FOR INSERT TO cornerpin_user WITH CHECK ({TENANT});
GRANT INSERT ON loans TO cornerpin_user;
CREATE POLICY loan_schedules_lend ON loan_schedules FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT});
GRANT INSERT ON loan_schedules TO cornerpin_user;
CREATE POLICY loan_payments_record ON loan_payments FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT} AND recorded_by = {ME});
GRANT INSERT ON loan_payments TO cornerpin_user;
"""  # noqa: S608 -- fixed SQL


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute(POLICIES)


def downgrade() -> None:
    op.execute(
        """
        REVOKE INSERT ON loan_payments FROM cornerpin_user;
        DROP POLICY loan_payments_record ON loan_payments;
        REVOKE INSERT ON loan_schedules FROM cornerpin_user;
        DROP POLICY loan_schedules_lend ON loan_schedules;
        REVOKE INSERT ON loans FROM cornerpin_user;
        DROP POLICY loans_lend ON loans;
        REVOKE INSERT ON financing_decisions FROM cornerpin_user;
        DROP POLICY financing_decisions_decide ON financing_decisions;
        DROP POLICY financing_decisions_own_read ON financing_decisions;
        REVOKE UPDATE (status) ON financing_applications FROM cornerpin_user;
        DROP POLICY financing_applications_decide ON financing_applications;
        REVOKE INSERT (id, tenant_id, lot_id, user_id, applicant_name, applicant_email, amount,
                       down_payment, term_months, income_band)
          ON financing_applications FROM cornerpin_user;
        DROP POLICY financing_applications_apply ON financing_applications;
        DROP POLICY financing_applications_own_read ON financing_applications;
        DROP INDEX financing_applications_one_open_idx;
        ALTER TABLE financing_decisions DROP COLUMN principal_reasons;

        GRANT cornerpin_worker TO CURRENT_USER WITH INHERIT TRUE;
        DROP FUNCTION app_tenant_offers_financing(uuid);
        REVOKE cornerpin_worker FROM CURRENT_USER;
        """
    )
