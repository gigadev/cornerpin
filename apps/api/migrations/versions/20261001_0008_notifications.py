"""notifications: lot changes queue an event, the worker reads what it sends, housekeeping

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01

ADR-029. A change to a lot's status or price queues `listings.lot_changed` from a trigger, in
the same transaction, so no code path can change a lot without savers hearing about it.
Anonymous inquiries queue `leads.inquiry_received`, and nothing else, as cornerpin_public.

cornerpin_worker reads the rows its handlers need (recipients, preferences, the lot itself),
removes push subscriptions the push service has dropped, and fans one event out into one per
recipient. Housekeeping deletes spent sign-in tokens and old processed events.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WORKER_READS = (
    "tenants",
    "users",
    "memberships",
    "subdivisions",
    "lots",
    "inquiries",
    "hold_requests",
    "saved_lots",
    "notification_prefs",
    "push_subscriptions",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION queue_lot_change() RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          BEGIN
            IF NEW.status IS DISTINCT FROM OLD.status OR NEW.price IS DISTINCT FROM OLD.price THEN
              INSERT INTO outbox (event_type, payload)
              VALUES ('listings.lot_changed', jsonb_build_object(
                'lot_id', NEW.id,
                'from_status', OLD.status, 'to_status', NEW.status,
                'from_price', OLD.price, 'to_price', NEW.price));
            END IF;
            RETURN NULL;
          END
          $$;
        CREATE TRIGGER lots_queue_change AFTER UPDATE OF status, price ON lots
          FOR EACH ROW EXECUTE FUNCTION queue_lot_change();

        CREATE POLICY outbox_public_enqueue ON outbox FOR INSERT TO cornerpin_public
          WITH CHECK (event_type = 'leads.inquiry_received');
        GRANT INSERT ON outbox TO cornerpin_public;

        GRANT INSERT, DELETE ON outbox TO cornerpin_worker;
        GRANT DELETE ON login_tokens TO cornerpin_auth;
        """
    )
    for table in WORKER_READS:
        op.execute(
            f"CREATE POLICY {table}_worker_read ON {table} FOR SELECT TO cornerpin_worker"
            f" USING (true); GRANT SELECT ON {table} TO cornerpin_worker"
        )
    op.execute(
        """
        CREATE POLICY push_subscriptions_worker_remove ON push_subscriptions FOR DELETE
          TO cornerpin_worker USING (true);
        GRANT DELETE ON push_subscriptions TO cornerpin_worker;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE DELETE ON push_subscriptions FROM cornerpin_worker;
        DROP POLICY push_subscriptions_worker_remove ON push_subscriptions;
        """
    )
    for table in WORKER_READS:
        op.execute(
            f"REVOKE SELECT ON {table} FROM cornerpin_worker;"  # noqa: S608 -- fixed names
            f" DROP POLICY {table}_worker_read ON {table}"
        )
    op.execute(
        """
        REVOKE DELETE ON login_tokens FROM cornerpin_auth;
        REVOKE INSERT, DELETE ON outbox FROM cornerpin_worker;
        REVOKE INSERT ON outbox FROM cornerpin_public;
        DROP POLICY outbox_public_enqueue ON outbox;
        DROP TRIGGER lots_queue_change ON lots;
        DROP FUNCTION queue_lot_change();
        """
    )
