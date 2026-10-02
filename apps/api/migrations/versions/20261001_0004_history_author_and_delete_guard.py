"""history keeps the author's email; buyer activity blocks deleting a lot

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

Users can read only their own row (ADR-021), so a portal page cannot look up who made an old
change. The trigger copies the author's email onto the history row when the change happens;
the author is the current user, whose row is visible to them (ADR-024).

Inquiries and hold requests used to cascade when their lot was deleted. They are buyer records
the owner must keep, so deleting a lot that has any is now refused by the database (ADR-024).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RESTRICT_LOT_DELETE = """
ALTER TABLE inquiries DROP CONSTRAINT inquiries_lot_id_tenant_id_fkey,
  ADD CONSTRAINT inquiries_lot_id_tenant_id_fkey FOREIGN KEY (lot_id, tenant_id)
  REFERENCES lots (id, tenant_id) ON DELETE RESTRICT;
ALTER TABLE hold_requests DROP CONSTRAINT hold_requests_lot_id_tenant_id_fkey,
  ADD CONSTRAINT hold_requests_lot_id_tenant_id_fkey FOREIGN KEY (lot_id, tenant_id)
  REFERENCES lots (id, tenant_id) ON DELETE RESTRICT;
"""

CASCADE_LOT_DELETE = RESTRICT_LOT_DELETE.replace("RESTRICT", "CASCADE")


def upgrade() -> None:
    op.execute(RESTRICT_LOT_DELETE)
    op.execute(
        """
        ALTER TABLE lot_status_history ADD COLUMN changed_by_email citext;
        ALTER TABLE lot_price_history ADD COLUMN changed_by_email citext;

        CREATE OR REPLACE FUNCTION record_lot_history() RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          DECLARE
            author uuid := app_user_id();
            author_email citext := (SELECT email FROM users WHERE id = app_user_id());
          BEGIN
            IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
              INSERT INTO lot_status_history
                (tenant_id, lot_id, from_status, to_status, changed_by, changed_by_email)
              VALUES (NEW.tenant_id, NEW.id, CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END,
                      NEW.status, author, author_email);
            END IF;
            IF TG_OP = 'INSERT' OR NEW.price IS DISTINCT FROM OLD.price THEN
              INSERT INTO lot_price_history
                (tenant_id, lot_id, from_price, to_price, changed_by, changed_by_email)
              VALUES (NEW.tenant_id, NEW.id, CASE WHEN TG_OP = 'UPDATE' THEN OLD.price END,
                      NEW.price, author, author_email);
            END IF;
            RETURN NULL;
          END
          $$;
        """
    )


def downgrade() -> None:
    op.execute(CASCADE_LOT_DELETE)
    op.execute(
        """
        CREATE OR REPLACE FUNCTION record_lot_history() RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          BEGIN
            IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
              INSERT INTO lot_status_history (tenant_id, lot_id, from_status, to_status,
                changed_by)
              VALUES (NEW.tenant_id, NEW.id,
                      CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END, NEW.status,
                      app_user_id());
            END IF;
            IF TG_OP = 'INSERT' OR NEW.price IS DISTINCT FROM OLD.price THEN
              INSERT INTO lot_price_history (tenant_id, lot_id, from_price, to_price, changed_by)
              VALUES (NEW.tenant_id, NEW.id,
                      CASE WHEN TG_OP = 'UPDATE' THEN OLD.price END, NEW.price, app_user_id());
            END IF;
            RETURN NULL;
          END
          $$;
        ALTER TABLE lot_price_history DROP COLUMN changed_by_email;
        ALTER TABLE lot_status_history DROP COLUMN changed_by_email;
        """
    )
