"""add trailing_stop, highest_price, breakeven_triggered to paper_positions

Revision ID: b8d5e3f6a1c9
Revises: e4b7c2f91a3d
Create Date: 2026-06-15 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d5e3f6a1c9"
down_revision: Union[str, None] = "e4b7c2f91a3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paper_positions",
        sa.Column("trailing_stop", sa.Numeric(24, 10), nullable=True),
    )
    op.add_column(
        "paper_positions",
        sa.Column("highest_price", sa.Numeric(24, 10), nullable=True),
    )
    op.add_column(
        "paper_positions",
        sa.Column("breakeven_triggered", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("paper_positions", "breakeven_triggered")
    op.drop_column("paper_positions", "highest_price")
    op.drop_column("paper_positions", "trailing_stop")
