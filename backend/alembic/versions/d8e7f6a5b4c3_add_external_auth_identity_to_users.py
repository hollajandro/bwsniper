"""Add external auth identity to users

Revision ID: d8e7f6a5b4c3
Revises: c2a1f9e4b8d3
Create Date: 2026-06-15 20:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8e7f6a5b4c3"
down_revision: Union[str, Sequence[str], None] = "c2a1f9e4b8d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_provider", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("external_subject", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_users_auth_provider_subject",
        "users",
        ["auth_provider", "external_subject"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_auth_provider_subject", table_name="users")
    op.drop_column("users", "external_subject")
    op.drop_column("users", "auth_provider")
