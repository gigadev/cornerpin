"""lot number collation

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02

ADR-034. Lot numbers sort the way people read them: "2-9" before "2-10" before "3-1", and
plain numbers before lettered ones ("10" before "B-1"). An ICU collation with numeric ordering
does it everywhere a query orders by lot number.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE COLLATION lot_number (provider = icu, locale = 'und-u-kn-true')")


def downgrade() -> None:
    op.execute("DROP COLLATION lot_number")
