"""lot geometry: acreage from the boundary, valid shapes only, plat overlays

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01

ADR-026. When a lot has a boundary, its acreage is the boundary's area, set by the database so
the two cannot disagree. A plat overlay is an image the owner lines up on the map to trace
lots over; it is owner-only and never public.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "tenant_id = (SELECT app_tenant_id())"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE lots ADD CONSTRAINT lots_boundary_valid
          CHECK (boundary IS NULL OR ST_IsValid(boundary));
        ALTER TABLE subdivisions ADD CONSTRAINT subdivisions_boundary_valid
          CHECK (boundary IS NULL OR ST_IsValid(boundary));

        CREATE FUNCTION set_lot_acreage() RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          BEGIN
            IF NEW.boundary IS NOT NULL THEN
              NEW.acreage := round((ST_Area(NEW.boundary::geography) / 4046.8564224)::numeric, 3);
            END IF;
            RETURN NEW;
          END
          $$;
        CREATE TRIGGER lots_acreage BEFORE INSERT OR UPDATE OF boundary ON lots
          FOR EACH ROW EXECUTE FUNCTION set_lot_acreage();

        -- Corners are [lng, lat] pairs in MapLibre's order: top-left, top-right, bottom-right,
        -- bottom-left.
        CREATE TABLE subdivision_overlays (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id      uuid NOT NULL,
          subdivision_id uuid NOT NULL UNIQUE,
          storage_key    text NOT NULL,
          content_type   text NOT NULL,
          width          integer NOT NULL CHECK (width > 0),
          height         integer NOT NULL CHECK (height > 0),
          corners        jsonb NOT NULL CHECK (
                           jsonb_typeof(corners) = 'array' AND jsonb_array_length(corners) = 4),
          opacity        real NOT NULL DEFAULT 0.6 CHECK (opacity BETWEEN 0 AND 1),
          created_at     timestamptz NOT NULL DEFAULT now(),
          updated_at     timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (subdivision_id, tenant_id)
            REFERENCES subdivisions (id, tenant_id) ON DELETE CASCADE
        );
        CREATE INDEX subdivision_overlays_tenant_id_idx ON subdivision_overlays (tenant_id);
        CREATE TRIGGER subdivision_overlays_updated_at BEFORE UPDATE ON subdivision_overlays
          FOR EACH ROW EXECUTE FUNCTION set_updated_at();

        ALTER TABLE subdivision_overlays ENABLE ROW LEVEL SECURITY;
        ALTER TABLE subdivision_overlays FORCE ROW LEVEL SECURITY;
        CREATE POLICY subdivision_overlays_tenant ON subdivision_overlays FOR ALL
          TO cornerpin_user USING ({TENANT}) WITH CHECK ({TENANT});
        GRANT SELECT, INSERT, UPDATE, DELETE ON subdivision_overlays TO cornerpin_user;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE subdivision_overlays;
        DROP TRIGGER lots_acreage ON lots;
        DROP FUNCTION set_lot_acreage();
        ALTER TABLE subdivisions DROP CONSTRAINT subdivisions_boundary_valid;
        ALTER TABLE lots DROP CONSTRAINT lots_boundary_valid;
        """
    )
