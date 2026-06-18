"""add exchange_stop_order_id, stop_placed_at to positions

Revision ID: f1a2b3c4d5e6
Revises: d2e4f6a8b0c1
Create Date: 2026-06-18 09:00:00.000000

Exchange-side stop orders: a stop resting on Gate.io protects a position even
when the scheduler is stuck/crashed or a fast adverse move gaps through the
15-min polling cadence. ``exchange_stop_order_id`` tracks the resting stop
(spot price-triggered order or futures conditional order); trailing/breakeven
amendments cancel+re-place it and update the id. ``stop_placed_at`` records when
the exchange stop was (re)placed, so staleness can be surfaced. Both nullable
so existing positions (opened before this migration) keep working in degraded
local-poll-only mode until they are amended.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d2e4f6a8b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("exchange_stop_order_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "positions",
        sa.Column("stop_placed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_positions_exchange_stop_order_id",
        "positions",
        ["exchange_stop_order_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_positions_exchange_stop_order_id", table_name="positions")
    op.drop_column("positions", "stop_placed_at")
    op.drop_column("positions", "exchange_stop_order_id")
