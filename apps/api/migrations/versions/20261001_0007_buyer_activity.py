"""buyer activity: only on public lots, anonymous inquiries, one pending hold, profile columns

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

ADR-028. A buyer can save, inquire about or ask to hold a lot only while the public can see it.
A signed-in buyer cannot see other tenants' lots through RLS, so the check is a function owned
by cornerpin_public: it sees exactly what an anonymous visitor sees, and returns only a boolean.

Anonymous visitors may file an inquiry (never anything else, and never one tied to a user).
Signed-in users may change only their name, phone and time zone, and may read the name of a
tenant they have recorded contact consent with.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SELF = "user_id = (SELECT app_user_id())"
PUBLIC_LOT = "app_lot_is_public(lot_id)"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION app_lot_is_public(lot uuid) RETURNS boolean
          LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
          AS $$ SELECT EXISTS (SELECT 1 FROM lots WHERE id = lot) $$;
        -- Handing a function to another role means being able to SET ROLE to it, and the new
        -- owner needs CREATE on its schema. A superuser skips both checks; a managed
        -- database's owner (Neon) administers the roles it created but can't act as them
        -- (Postgres 16+). Both are granted only for the hand-over.
        GRANT cornerpin_public TO CURRENT_USER WITH INHERIT FALSE, SET TRUE;
        GRANT CREATE ON SCHEMA public TO cornerpin_public;
        ALTER FUNCTION app_lot_is_public(uuid) OWNER TO cornerpin_public;
        REVOKE CREATE ON SCHEMA public FROM cornerpin_public;
        REVOKE cornerpin_public FROM CURRENT_USER;
        REVOKE ALL ON FUNCTION app_lot_is_public(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION app_lot_is_public(uuid) TO cornerpin_user, cornerpin_public;

        DROP POLICY saved_lots_self ON saved_lots;
        CREATE POLICY saved_lots_self_read ON saved_lots FOR SELECT TO cornerpin_user
          USING ({SELF});
        CREATE POLICY saved_lots_self_delete ON saved_lots FOR DELETE TO cornerpin_user
          USING ({SELF});
        CREATE POLICY saved_lots_self_create ON saved_lots FOR INSERT TO cornerpin_user
          WITH CHECK ({SELF} AND {PUBLIC_LOT});
        REVOKE UPDATE ON saved_lots FROM cornerpin_user;

        ALTER POLICY inquiries_create ON inquiries WITH CHECK ({SELF} AND {PUBLIC_LOT});
        CREATE POLICY inquiries_anonymous ON inquiries FOR INSERT TO cornerpin_public
          WITH CHECK (user_id IS NULL AND {PUBLIC_LOT});
        GRANT INSERT ON inquiries TO cornerpin_public;

        ALTER POLICY hold_requests_create ON hold_requests
          WITH CHECK ({SELF} AND {PUBLIC_LOT} AND status = 'pending' AND decided_by IS NULL);
        CREATE UNIQUE INDEX hold_requests_one_pending_idx ON hold_requests (lot_id, user_id)
          WHERE status = 'pending';

        REVOKE UPDATE ON users FROM cornerpin_user;
        GRANT UPDATE (display_name, phone, time_zone) ON users TO cornerpin_user;

        CREATE POLICY tenants_contacted ON tenants FOR SELECT TO cornerpin_user
          USING (id IN (SELECT tenant_id FROM contact_consents WHERE {SELF}));
        """  # noqa: S608 -- interpolates only the SELF and PUBLIC_LOT constants
    )


def downgrade() -> None:
    op.execute(
        f"""
        DROP POLICY tenants_contacted ON tenants;
        GRANT UPDATE ON users TO cornerpin_user;

        DROP INDEX hold_requests_one_pending_idx;
        ALTER POLICY hold_requests_create ON hold_requests WITH CHECK ({SELF});

        REVOKE INSERT ON inquiries FROM cornerpin_public;
        DROP POLICY inquiries_anonymous ON inquiries;
        ALTER POLICY inquiries_create ON inquiries WITH CHECK ({SELF});

        GRANT UPDATE ON saved_lots TO cornerpin_user;
        DROP POLICY saved_lots_self_create ON saved_lots;
        DROP POLICY saved_lots_self_delete ON saved_lots;
        DROP POLICY saved_lots_self_read ON saved_lots;
        CREATE POLICY saved_lots_self ON saved_lots FOR ALL TO cornerpin_user
          USING ({SELF}) WITH CHECK ({SELF});

        DROP FUNCTION app_lot_is_public(uuid);
        """
    )
