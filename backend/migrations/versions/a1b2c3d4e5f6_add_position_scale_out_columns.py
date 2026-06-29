"""add initial_stop_loss, scaled_out to positions

Revision ID: c3d4e5f6a7b8
Revises: f1a2b3c4d5e6
Create Date: 2026-06-19 10:00:00.000000

Partial profit taking (scale-out): close a fraction of a position once it reaches
a configured R-multiple of profit, then ride the remainder risk-free. R is the
INITIAL risk-per-unit, so ``initial_stop_loss`` preserves the entry stop even
after trailing/breakeven move ``stop_loss``. ``scaled_out`` ensures the partial
fires at most once. Both nullable/defaulted so pre-existing open positions keep
working (they simply never scale out — their R baseline is unknown).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("initial_stop_loss", sa.Numeric(24, 10), nullable=True),
    )
    op.add_column(
        "positions",
        sa.Column(
            "scaled_out", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("positions", "scaled_out")
    op.drop_column("positions", "initial_stop_loss")
