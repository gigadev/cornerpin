"""phase 1 schema, roles and row-level security

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01

Roles (ADR-021):
  cornerpin_api     LOGIN NOINHERIT; holds no privileges itself, so a transaction that forgets
                    SET LOCAL ROLE fails closed.
  cornerpin_user    signed-in users. Tenant rows only for a tenant the user is a member of;
                    a buyer's own rows by user id.
  cornerpin_public  anonymous reads of published listings only.

Every tenant-owned table has tenant_id uuid not null, RLS enabled and forced, and composite
foreign keys that keep tenant_id consistent with its parent.
"""

from collections.abc import Sequence

from alembic import op
from psycopg import sql
from sqlalchemy.engine import make_url

from cornerpin.core.config import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = """
CREATE EXTENSION IF NOT EXISTS citext;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_user') THEN
    CREATE ROLE cornerpin_user NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_public') THEN
    CREATE ROLE cornerpin_public NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cornerpin_api') THEN
    CREATE ROLE cornerpin_api LOGIN NOINHERIT;
  END IF;
END
$$;

GRANT cornerpin_user, cornerpin_public TO cornerpin_api;
GRANT USAGE ON SCHEMA public TO cornerpin_user, cornerpin_public;
"""

# Session context. app_tenant_id() only returns the tenant when the current user is a member of
# it, so a wrong app.tenant_id from a bug in the API still exposes nothing.
FUNCTIONS = """
CREATE FUNCTION app_user_id() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

CREATE FUNCTION app_tenant_id() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$
    SELECT m.tenant_id
    FROM memberships m
    WHERE m.tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid
      AND m.user_id = app_user_id()
  $$;

CREATE FUNCTION set_updated_at() RETURNS trigger
  LANGUAGE plpgsql
  AS $$ BEGIN NEW.updated_at := now(); RETURN NEW; END $$;
"""

TYPES = """
CREATE TYPE membership_role AS ENUM ('owner', 'staff');
CREATE TYPE phase_release_status AS ENUM ('upcoming', 'released');
CREATE TYPE lot_status AS ENUM ('available', 'on_hold', 'sold');
CREATE TYPE listing_type AS ENUM ('land_only', 'lot_and_home');
CREATE TYPE lot_document_kind AS ENUM ('plat', 'survey', 'covenants', 'utilities', 'other');
CREATE TYPE hold_request_status AS ENUM ('pending', 'approved', 'declined', 'withdrawn');
CREATE TYPE contact_channel AS ENUM ('email', 'sms', 'voice');
"""

TABLES = """
CREATE TABLE tenants (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  is_demo    boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email             citext NOT NULL UNIQUE,
  display_name      text,
  phone             text CHECK (phone ~ '^\\+[1-9][0-9]{6,14}$'),
  time_zone         text,
  email_verified_at timestamptz,
  created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
  tenant_id  uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  role       membership_role NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id)
);
CREATE INDEX memberships_user_id_idx ON memberships (user_id);

CREATE TABLE subdivisions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  name        text NOT NULL,
  slug        text NOT NULL UNIQUE
              CHECK (slug ~ '^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$')
              CHECK (slug NOT IN ('app', 'q', 'api', 'v1', 'graphql', 'internal', 'serwist',
                                  'icons', 'static', 'admin', 'auth', 'login', 'logout',
                                  'signin', 'signup', 'account', 'settings', 'about', 'help',
                                  'terms', 'privacy', 'offline')),
  location    geometry(Point, 4326) NOT NULL,
  boundary    geometry(MultiPolygon, 4326),
  time_zone   text NOT NULL,
  description text NOT NULL DEFAULT '',
  published   boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, tenant_id)
);
CREATE INDEX subdivisions_tenant_id_idx ON subdivisions (tenant_id);

CREATE TABLE phases (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id      uuid NOT NULL,
  subdivision_id uuid NOT NULL,
  name           text NOT NULL,
  sort_order     integer NOT NULL DEFAULT 0,
  release_status phase_release_status NOT NULL DEFAULT 'upcoming',
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (id, tenant_id),
  UNIQUE (id, subdivision_id),
  FOREIGN KEY (subdivision_id, tenant_id)
    REFERENCES subdivisions (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX phases_tenant_id_idx ON phases (tenant_id);
CREATE INDEX phases_subdivision_id_idx ON phases (subdivision_id);

CREATE TABLE lots (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  subdivision_id    uuid NOT NULL,
  phase_id          uuid NOT NULL,
  number            text NOT NULL CHECK (number ~ '^[A-Za-z0-9-]{1,16}$'),
  boundary          geometry(MultiPolygon, 4326),
  acreage           numeric(9, 3) CHECK (acreage > 0),
  price             numeric(12, 2) CHECK (price >= 0),
  status            lot_status NOT NULL DEFAULT 'available',
  listing_type      listing_type NOT NULL DEFAULT 'land_only',
  home_bedrooms     smallint CHECK (home_bedrooms >= 0),
  home_bathrooms    numeric(3, 1) CHECK (home_bathrooms >= 0),
  home_square_feet  integer CHECK (home_square_feet > 0),
  home_description  text,
  published         boolean NOT NULL DEFAULT false,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (subdivision_id, number),
  UNIQUE (id, tenant_id),
  FOREIGN KEY (subdivision_id, tenant_id)
    REFERENCES subdivisions (id, tenant_id) ON DELETE CASCADE,
  FOREIGN KEY (phase_id, subdivision_id)
    REFERENCES phases (id, subdivision_id) ON DELETE CASCADE,
  CHECK (listing_type = 'lot_and_home' OR (home_bedrooms IS NULL AND home_bathrooms IS NULL
         AND home_square_feet IS NULL AND home_description IS NULL))
);
CREATE INDEX lots_tenant_id_idx ON lots (tenant_id);
CREATE INDEX lots_phase_id_idx ON lots (phase_id);
CREATE INDEX lots_boundary_idx ON lots USING gist (boundary);

CREATE TABLE lot_status_history (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL,
  lot_id      uuid NOT NULL,
  from_status lot_status,
  to_status   lot_status NOT NULL,
  changed_by  uuid REFERENCES users ON DELETE SET NULL,
  changed_at  timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX lot_status_history_lot_id_idx ON lot_status_history (lot_id, changed_at);
CREATE INDEX lot_status_history_tenant_id_idx ON lot_status_history (tenant_id);

CREATE TABLE lot_price_history (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  lot_id     uuid NOT NULL,
  from_price numeric(12, 2),
  to_price   numeric(12, 2),
  changed_by uuid REFERENCES users ON DELETE SET NULL,
  changed_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX lot_price_history_lot_id_idx ON lot_price_history (lot_id, changed_at);
CREATE INDEX lot_price_history_tenant_id_idx ON lot_price_history (tenant_id);

CREATE TABLE lot_media (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  lot_id       uuid NOT NULL,
  storage_key  text NOT NULL,
  content_type text NOT NULL,
  caption      text NOT NULL DEFAULT '',
  sort_order   integer NOT NULL DEFAULT 0,
  width        integer CHECK (width > 0),
  height       integer CHECK (height > 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX lot_media_lot_id_idx ON lot_media (lot_id, sort_order);
CREATE INDEX lot_media_tenant_id_idx ON lot_media (tenant_id);

CREATE TABLE lot_documents (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL,
  lot_id       uuid NOT NULL,
  kind         lot_document_kind NOT NULL,
  title        text NOT NULL,
  storage_key  text NOT NULL,
  content_type text NOT NULL,
  size_bytes   bigint NOT NULL CHECK (size_bytes >= 0),
  created_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX lot_documents_lot_id_idx ON lot_documents (lot_id);
CREATE INDEX lot_documents_tenant_id_idx ON lot_documents (tenant_id);

CREATE TABLE saved_lots (
  user_id    uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  lot_id     uuid NOT NULL,
  tenant_id  uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, lot_id),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX saved_lots_lot_id_idx ON saved_lots (lot_id);
CREATE INDEX saved_lots_tenant_id_idx ON saved_lots (tenant_id);

CREATE TABLE inquiries (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  lot_id     uuid NOT NULL,
  user_id    uuid REFERENCES users ON DELETE SET NULL,
  name       text NOT NULL,
  email      citext NOT NULL,
  phone      text CHECK (phone ~ '^\\+[1-9][0-9]{6,14}$'),
  message    text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX inquiries_tenant_id_idx ON inquiries (tenant_id, created_at);
CREATE INDEX inquiries_user_id_idx ON inquiries (user_id);

CREATE TABLE hold_requests (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  lot_id     uuid NOT NULL,
  user_id    uuid REFERENCES users ON DELETE SET NULL,
  name       text NOT NULL,
  email      citext NOT NULL,
  phone      text CHECK (phone ~ '^\\+[1-9][0-9]{6,14}$'),
  message    text NOT NULL DEFAULT '',
  status     hold_request_status NOT NULL DEFAULT 'pending',
  decided_by uuid REFERENCES users ON DELETE SET NULL,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE,
  CHECK ((status IN ('pending', 'withdrawn')) = (decided_at IS NULL))
);
CREATE INDEX hold_requests_tenant_id_idx ON hold_requests (tenant_id, created_at);
CREATE INDEX hold_requests_user_id_idx ON hold_requests (user_id);

-- Append-only: the latest row per (tenant, user, channel) is the current consent (ADR-022).
CREATE TABLE contact_consents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  channel     contact_channel NOT NULL,
  granted     boolean NOT NULL,
  source      text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX contact_consents_lookup_idx
  ON contact_consents (tenant_id, user_id, channel, recorded_at DESC);
CREATE INDEX contact_consents_user_id_idx ON contact_consents (user_id);

CREATE TABLE notification_prefs (
  user_id                 uuid PRIMARY KEY REFERENCES users ON DELETE CASCADE,
  email_saved_lot_changes boolean NOT NULL DEFAULT true,
  push_saved_lot_changes  boolean NOT NULL DEFAULT false,
  updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE push_subscriptions (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES users ON DELETE CASCADE,
  endpoint   text NOT NULL UNIQUE,
  p256dh     text NOT NULL,
  auth       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX push_subscriptions_user_id_idx ON push_subscriptions (user_id);

CREATE TABLE qr_codes (
  code       text PRIMARY KEY CHECK (code ~ '^[a-z0-9]{6,16}$'),
  tenant_id  uuid NOT NULL,
  lot_id     uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (lot_id, tenant_id) REFERENCES lots (id, tenant_id) ON DELETE CASCADE
);
CREATE INDEX qr_codes_lot_id_idx ON qr_codes (lot_id);
CREATE INDEX qr_codes_tenant_id_idx ON qr_codes (tenant_id);
"""

TRIGGERS = """
CREATE TRIGGER subdivisions_updated_at BEFORE UPDATE ON subdivisions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER phases_updated_at BEFORE UPDATE ON phases
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER lots_updated_at BEFORE UPDATE ON lots
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER notification_prefs_updated_at BEFORE UPDATE ON notification_prefs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- History is written by the database so no code path can change status or price without it.
CREATE FUNCTION record_lot_history() RETURNS trigger
  LANGUAGE plpgsql
  AS $$
  BEGIN
    IF TG_OP = 'INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
      INSERT INTO lot_status_history (tenant_id, lot_id, from_status, to_status, changed_by)
      VALUES (NEW.tenant_id, NEW.id,
              CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END, NEW.status, app_user_id());
    END IF;
    IF TG_OP = 'INSERT' OR NEW.price IS DISTINCT FROM OLD.price THEN
      INSERT INTO lot_price_history (tenant_id, lot_id, from_price, to_price, changed_by)
      VALUES (NEW.tenant_id, NEW.id,
              CASE WHEN TG_OP = 'UPDATE' THEN OLD.price END, NEW.price, app_user_id());
    END IF;
    RETURN NULL;
  END
  $$;

CREATE TRIGGER lots_history AFTER INSERT OR UPDATE OF status, price ON lots
  FOR EACH ROW EXECUTE FUNCTION record_lot_history();
"""

# Tables whose rows belong to one tenant. tenants is keyed by id rather than tenant_id.
TENANT_TABLES = (
    "memberships",
    "subdivisions",
    "phases",
    "lots",
    "lot_status_history",
    "lot_price_history",
    "lot_media",
    "lot_documents",
    "saved_lots",
    "inquiries",
    "hold_requests",
    "contact_consents",
    "qr_codes",
)
USER_TABLES = ("users", "notification_prefs", "push_subscriptions")

# (SELECT f()) makes Postgres evaluate the context once per query instead of once per row.
TENANT = "tenant_id = (SELECT app_tenant_id())"
SELF = "user_id = (SELECT app_user_id())"

POLICIES = f"""
-- tenants: the ones the user belongs to.
CREATE POLICY tenants_member ON tenants FOR SELECT TO cornerpin_user
  USING (id IN (SELECT tenant_id FROM memberships));

-- memberships: only the user's own. (A policy here may not query memberships again.)
CREATE POLICY memberships_self ON memberships FOR SELECT TO cornerpin_user USING ({SELF});

-- users and per-user settings: only yourself.
CREATE POLICY users_self_read ON users FOR SELECT TO cornerpin_user
  USING (id = (SELECT app_user_id()));
CREATE POLICY users_self_update ON users FOR UPDATE TO cornerpin_user
  USING (id = (SELECT app_user_id())) WITH CHECK (id = (SELECT app_user_id()));
CREATE POLICY notification_prefs_self ON notification_prefs FOR ALL TO cornerpin_user
  USING ({SELF}) WITH CHECK ({SELF});
CREATE POLICY push_subscriptions_self ON push_subscriptions FOR ALL TO cornerpin_user
  USING ({SELF}) WITH CHECK ({SELF});

-- Listings: owners and staff manage their tenant's rows.
CREATE POLICY subdivisions_tenant ON subdivisions FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY phases_tenant ON phases FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY lots_tenant ON lots FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY lot_media_tenant ON lot_media FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY lot_documents_tenant ON lot_documents FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});
CREATE POLICY qr_codes_tenant ON qr_codes FOR ALL TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});

-- History: readable by the tenant, written only by the lots trigger.
CREATE POLICY lot_status_history_read ON lot_status_history FOR SELECT TO cornerpin_user
  USING ({TENANT});
CREATE POLICY lot_status_history_write ON lot_status_history FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT});
CREATE POLICY lot_price_history_read ON lot_price_history FOR SELECT TO cornerpin_user
  USING ({TENANT});
CREATE POLICY lot_price_history_write ON lot_price_history FOR INSERT TO cornerpin_user
  WITH CHECK ({TENANT});

-- Buyer activity: the buyer sees their own rows; the tenant sees rows about its lots.
-- The composite foreign key to lots forces tenant_id to match the lot's tenant.
CREATE POLICY saved_lots_self ON saved_lots FOR ALL TO cornerpin_user
  USING ({SELF}) WITH CHECK ({SELF});
CREATE POLICY saved_lots_tenant ON saved_lots FOR SELECT TO cornerpin_user USING ({TENANT});

CREATE POLICY inquiries_read ON inquiries FOR SELECT TO cornerpin_user
  USING ({TENANT} OR {SELF});
CREATE POLICY inquiries_create ON inquiries FOR INSERT TO cornerpin_user WITH CHECK ({SELF});

CREATE POLICY hold_requests_read ON hold_requests FOR SELECT TO cornerpin_user
  USING ({TENANT} OR {SELF});
CREATE POLICY hold_requests_create ON hold_requests FOR INSERT TO cornerpin_user
  WITH CHECK ({SELF});
CREATE POLICY hold_requests_decide ON hold_requests FOR UPDATE TO cornerpin_user
  USING ({TENANT}) WITH CHECK ({TENANT});

CREATE POLICY contact_consents_read ON contact_consents FOR SELECT TO cornerpin_user
  USING ({SELF} OR {TENANT});
CREATE POLICY contact_consents_record ON contact_consents FOR INSERT TO cornerpin_user
  WITH CHECK ({SELF});

-- Public: published listings only. Subqueries are themselves filtered by these policies, so a
-- published lot in an unpublished subdivision stays hidden.
CREATE POLICY subdivisions_public ON subdivisions FOR SELECT TO cornerpin_public
  USING (published);
CREATE POLICY phases_public ON phases FOR SELECT TO cornerpin_public
  USING (EXISTS (SELECT 1 FROM subdivisions s WHERE s.id = phases.subdivision_id));
CREATE POLICY lots_public ON lots FOR SELECT TO cornerpin_public
  USING (published AND EXISTS (SELECT 1 FROM subdivisions s WHERE s.id = lots.subdivision_id));
CREATE POLICY lot_media_public ON lot_media FOR SELECT TO cornerpin_public
  USING (EXISTS (SELECT 1 FROM lots l WHERE l.id = lot_media.lot_id));
CREATE POLICY lot_documents_public ON lot_documents FOR SELECT TO cornerpin_public
  USING (EXISTS (SELECT 1 FROM lots l WHERE l.id = lot_documents.lot_id));
CREATE POLICY qr_codes_public ON qr_codes FOR SELECT TO cornerpin_public
  USING (EXISTS (SELECT 1 FROM lots l WHERE l.id = qr_codes.lot_id));
"""  # noqa: S608 -- interpolates only the TENANT and SELF constants

GRANTS = """
GRANT SELECT ON tenants, memberships TO cornerpin_user;
GRANT SELECT, UPDATE ON users TO cornerpin_user;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON subdivisions, phases, lots, lot_media, lot_documents, qr_codes,
     saved_lots, notification_prefs, push_subscriptions
  TO cornerpin_user;
GRANT SELECT, INSERT ON lot_status_history, lot_price_history, contact_consents
  TO cornerpin_user;
GRANT SELECT, INSERT ON inquiries TO cornerpin_user;
GRANT SELECT, INSERT, UPDATE ON hold_requests TO cornerpin_user;

GRANT SELECT ON subdivisions, phases, lots, lot_media, lot_documents, qr_codes
  TO cornerpin_public;
"""


def upgrade() -> None:
    op.execute(ROLES)
    op.execute(TYPES)
    op.execute(TABLES)
    op.execute(FUNCTIONS)  # after TABLES: app_tenant_id() reads memberships
    op.execute(TRIGGERS)
    for table in ("tenants", *TENANT_TABLES, *USER_TABLES):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(POLICIES)
    op.execute(GRANTS)
    _set_local_api_password()


def _set_local_api_password() -> None:
    """Locally, give cornerpin_api the password from API_DATABASE_URL so the API can log in.
    In the cloud the role's password is provisioned with the infrastructure (P1-12)."""
    settings = get_settings()
    if settings.environment != "local":
        return
    url = make_url(settings.api_database_url)
    if url.username != "cornerpin_api" or not url.password:
        return
    # ALTER ROLE takes no bind parameters, so let psycopg quote the literal.
    statement = sql.SQL("ALTER ROLE cornerpin_api PASSWORD {}").format(sql.Literal(url.password))
    op.get_bind().exec_driver_sql(statement.as_string())


def downgrade() -> None:
    # Roles are cluster-wide and may serve other databases (e.g. the test database), so they
    # are left in place.
    op.execute(
        """
        DROP TABLE qr_codes, push_subscriptions, notification_prefs, contact_consents,
          hold_requests, inquiries, saved_lots, lot_documents, lot_media, lot_price_history,
          lot_status_history, lots, phases, subdivisions, memberships, users, tenants;
        DROP FUNCTION record_lot_history(), set_updated_at(), app_tenant_id(), app_user_id();
        DROP TYPE contact_channel, hold_request_status, lot_document_kind, listing_type,
          lot_status, phase_release_status, membership_role;
        """
    )
