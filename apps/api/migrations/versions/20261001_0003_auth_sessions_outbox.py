"""auth: login tokens, sessions, and a minimal outbox

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

Adds two group roles (ADR-023):
  cornerpin_auth    sign-in and session lookup, which happen before a user is known.
  cornerpin_worker  the outbox runner.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_auth') THEN
    CREATE ROLE cornerpin_auth NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_worker') THEN
    CREATE ROLE cornerpin_worker NOLOGIN;
  END IF;
END
$$;

GRANT cornerpin_auth, cornerpin_worker TO cornerpin_api;
GRANT USAGE ON SCHEMA public TO cornerpin_auth, cornerpin_worker;
"""

TABLES = """
-- Only hashes are stored; the raw token exists in the email link alone.
CREATE TABLE login_tokens (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash   bytea NOT NULL UNIQUE,
  email        citext NOT NULL,
  next_path    text NOT NULL DEFAULT '/',
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  used_at      timestamptz
);
CREATE INDEX login_tokens_email_idx ON login_tokens (email, created_at);

CREATE TABLE sessions (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash   bytea NOT NULL UNIQUE,
  user_id      uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  user_agent   text
);
CREATE INDEX sessions_user_id_idx ON sessions (user_id);

-- Written in the same transaction as the change that causes it (ADR-010). No tenant_id
-- column: events that concern a tenant carry it in the payload, and only the worker reads.
CREATE TABLE outbox (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type   text NOT NULL,
  payload      jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  available_at timestamptz NOT NULL DEFAULT now(),
  attempts     integer NOT NULL DEFAULT 0,
  last_error   text,
  processed_at timestamptz
);
CREATE INDEX outbox_pending_idx ON outbox (available_at) WHERE processed_at IS NULL;
"""

POLICIES = """
ALTER TABLE login_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox FORCE ROW LEVEL SECURITY;

CREATE POLICY login_tokens_auth ON login_tokens FOR ALL TO cornerpin_auth
  USING (true) WITH CHECK (true);
CREATE POLICY sessions_auth ON sessions FOR ALL TO cornerpin_auth
  USING (true) WITH CHECK (true);
CREATE POLICY users_auth_read ON users FOR SELECT TO cornerpin_auth USING (true);
CREATE POLICY users_auth_create ON users FOR INSERT TO cornerpin_auth WITH CHECK (true);
CREATE POLICY users_auth_verify ON users FOR UPDATE TO cornerpin_auth
  USING (true) WITH CHECK (true);

CREATE POLICY outbox_auth_enqueue ON outbox FOR INSERT TO cornerpin_auth WITH CHECK (true);
CREATE POLICY outbox_worker ON outbox FOR ALL TO cornerpin_worker
  USING (true) WITH CHECK (true);
"""

GRANTS = """
GRANT SELECT, INSERT, UPDATE ON login_tokens TO cornerpin_auth;
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO cornerpin_auth;
GRANT SELECT, INSERT ON users TO cornerpin_auth;
GRANT UPDATE (email_verified_at) ON users TO cornerpin_auth;
GRANT INSERT ON outbox TO cornerpin_auth;
GRANT SELECT, UPDATE ON outbox TO cornerpin_worker;
"""


def upgrade() -> None:
    op.execute(ROLES)
    op.execute(TABLES)
    op.execute(POLICIES)
    op.execute(GRANTS)


def downgrade() -> None:
    op.execute(
        """
        DROP POLICY users_auth_read ON users;
        DROP POLICY users_auth_create ON users;
        DROP POLICY users_auth_verify ON users;
        REVOKE ALL ON users FROM cornerpin_auth;
        DROP TABLE outbox, sessions, login_tokens;
        """
    )
