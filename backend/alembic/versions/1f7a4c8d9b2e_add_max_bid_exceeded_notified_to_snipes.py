"""Add max bid exceeded notification flag to snipes

Revision ID: 1f7a4c8d9b2e
Revises: 79a77033015d
Create Date: 2026-04-22 20:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1f7a4c8d9b2e"
down_revision: Union[str, Sequence[str], None] = "79a77033015d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "snipes",
        sa.Column(
            "max_bid_exceeded_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("snipes", "max_bid_exceeded_notified", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("snipes", "max_bid_exceeded_notified")
