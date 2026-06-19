"""raise deployed strategy_settings risk to the new defaults

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20 12:00:00.000000

The ``strategy_settings`` row is created ONCE (first access) with the model
defaults; later raising those defaults in code does NOT migrate an existing
deployed row. The risk-appetite bump in c393ef5 therefore never reached the
live DB. This one-time data migration applies the raised risk values to the
existing row.

Guarded so it only RAISES and never clobbers a manual change: each column is
updated only where the current value is still at/below the OLD default (a user
who already tuned a knob higher in the dashboard keeps their value). All targets
stay within the existing CheckConstraints (max_capital_per_trade_pct <= 0.20,
weekly_max_loss_pct <= 0.30).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Notional cap per trade: 0.05 -> 0.08 (<= 0.20 ceiling).
    op.execute(
        "UPDATE strategy_settings SET max_capital_per_trade_pct = 0.08 "
        "WHERE max_capital_per_trade_pct <= 0.05"
    )
    # Weekly loss budget: 0.15 -> 0.18 (<= 0.30 ceiling).
    op.execute(
        "UPDATE strategy_settings SET weekly_max_loss_pct = 0.18 "
        "WHERE weekly_max_loss_pct <= 0.15"
    )
    # Wider book: 8 -> 10 open positions.
    op.execute(
        "UPDATE strategy_settings SET max_open_positions = 10 "
        "WHERE max_open_positions <= 8"
    )


def downgrade() -> None:
    # Best-effort revert to the pre-bump values (only where they match the
    # raised targets, so a later manual change is not stomped).
    op.execute(
        "UPDATE strategy_settings SET max_capital_per_trade_pct = 0.05 "
        "WHERE max_capital_per_trade_pct = 0.08"
    )
    op.execute(
        "UPDATE strategy_settings SET weekly_max_loss_pct = 0.15 "
        "WHERE weekly_max_loss_pct = 0.18"
    )
    op.execute(
        "UPDATE strategy_settings SET max_open_positions = 8 "
        "WHERE max_open_positions = 10"
    )
