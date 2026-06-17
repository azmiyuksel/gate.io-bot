"""add worker_heartbeats

Revision ID: d2e4f6a8b0c1
Revises: c1f2a3b4d5e6
Create Date: 2026-06-17 10:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2e4f6a8b0c1"
down_revision: Union[str, None] = "c1f2a3b4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("worker", sa.String(length=64), nullable=False),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_worker_heartbeats_worker"), "worker_heartbeats", ["worker"], unique=True)
    op.create_index(
        op.f("ix_worker_heartbeats_last_beat_at"), "worker_heartbeats", ["last_beat_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_worker_heartbeats_last_beat_at"), table_name="worker_heartbeats")
    op.drop_index(op.f("ix_worker_heartbeats_worker"), table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
