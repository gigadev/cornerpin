"""one QR code per lot

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01

ADR-031. A lot's code is created the first time its sign is opened and never changes, so a
printed sign keeps working through slug renames. One code per lot keeps "get or create" safe
when two people open the sign at once.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DROP INDEX qr_codes_lot_id_idx;
        CREATE UNIQUE INDEX qr_codes_lot_id_key ON qr_codes (lot_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX qr_codes_lot_id_key;
        CREATE INDEX qr_codes_lot_id_idx ON qr_codes (lot_id);
        """
    )
