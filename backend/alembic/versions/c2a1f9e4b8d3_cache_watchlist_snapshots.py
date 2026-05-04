"""Cache watchlist auction snapshots

Revision ID: c2a1f9e4b8d3
Revises: a3d9c5e6f742
Create Date: 2026-04-25 22:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2a1f9e4b8d3"
down_revision: Union[str, Sequence[str], None] = "a3d9c5e6f742"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("watchlist", sa.Column("auction_id", sa.String(length=64), nullable=True))
    op.add_column("watchlist", sa.Column("snapshot_json", sa.Text(), nullable=True))
    op.create_index("ix_watchlist_user_handle", "watchlist", ["user_id", "handle"], unique=False)
    op.create_index("ix_watchlist_user_auction", "watchlist", ["user_id", "auction_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watchlist_user_auction", table_name="watchlist")
    op.drop_index("ix_watchlist_user_handle", table_name="watchlist")
    op.drop_column("watchlist", "snapshot_json")
    op.drop_column("watchlist", "auction_id")
