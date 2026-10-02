"""signed-in users may queue outbox events (but not sign-in emails)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

The owner portal queues work in the same transaction as a change, starting with removing
stored files after their photo or document row is deleted (ADR-025). Events in the auth.*
namespace stay reserved for cornerpin_auth, so this cannot be used to send sign-in links.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY outbox_user_enqueue ON outbox FOR INSERT TO cornerpin_user
          WITH CHECK (event_type NOT LIKE 'auth.%');
        GRANT INSERT ON outbox TO cornerpin_user;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        REVOKE INSERT ON outbox FROM cornerpin_user;
        DROP POLICY outbox_user_enqueue ON outbox;
        """
    )
