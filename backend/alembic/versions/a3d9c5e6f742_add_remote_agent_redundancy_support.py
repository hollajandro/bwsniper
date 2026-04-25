"""Add remote agent redundancy support

Revision ID: a3d9c5e6f742
Revises: 1f7a4c8d9b2e
Create Date: 2026-04-23 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3d9c5e6f742"
down_revision: Union[str, Sequence[str], None] = "1f7a4c8d9b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "remote_agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("api_key_hash", sa.String(length=64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("clock_offset_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.add_column(
        "users",
        sa.Column(
            "remote_redundancy_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("remote_agent_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_users_remote_agent_id_remote_agents",
        "users",
        "remote_agents",
        ["remote_agent_id"],
        ["id"],
    )
    op.alter_column("users", "remote_redundancy_enabled", server_default=None)

    op.create_table(
        "remote_snipe_state",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("snipe_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["remote_agents.id"]),
        sa.ForeignKeyConstraint(["snipe_id"], ["snipes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_remote_snipe_state_agent",
        "remote_snipe_state",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "ix_remote_snipe_state_snipe",
        "remote_snipe_state",
        ["snipe_id"],
        unique=False,
    )
    op.create_index(
        "ix_remote_snipe_state_agent_snipe",
        "remote_snipe_state",
        ["agent_id", "snipe_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_remote_snipe_state_agent_snipe", table_name="remote_snipe_state")
    op.drop_index("ix_remote_snipe_state_snipe", table_name="remote_snipe_state")
    op.drop_index("ix_remote_snipe_state_agent", table_name="remote_snipe_state")
    op.drop_table("remote_snipe_state")

    op.drop_constraint(
        "fk_users_remote_agent_id_remote_agents",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "remote_agent_id")
    op.drop_column("users", "remote_redundancy_enabled")

    op.drop_table("remote_agents")
