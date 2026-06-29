"""paper realism: liquidation, signed funding, hedge mode, order types/TIF/OCO

Revision ID: a1b2c3d4e5f6
Revises: e5f6a7b8c9d0
Create Date: 2026-06-29 00:00:00.000000

Critical realism gaps for the paper trading engine:

1. Liquidation (single-tier maintenance margin): ``paper_positions`` gains
   ``leverage``, ``margin`` (isolated/cross posted margin), ``liquidation_price``
   and ``mark_price`` so the engine can force-close leveraged losers when mark
   crosses maintenance — instead of letting equity go unboundedly negative.

2. Signed 8-hourly funding accrual: ``last_funding_ts`` + ``last_funding_rate``
   on positions let funding settle every 8h into equity (signed — longs pay
   shorts when rate > 0), not once at close as a flat positive daily tax.

3. Hedge mode (one-way vs dual-side): ``paper_accounts.position_mode`` selects
   between the existing netting auto-flip behaviour and true hedge (long and
   short open simultaneously on the same symbol). ``margin_mode`` records
   cross/isolated for documentation parity with live accounts.

4. Order types / TIF / OCO / reduce-only / post-only: ``paper_orders`` gains
   ``time_in_force`` (GTC/IOC/FOK/POST_ONLY), ``reduce_only``, ``post_only``,
   ``linked_order_id`` (OCO pair) and ``position_side`` (long/short for hedge).

All columns are nullable / have safe defaults so existing paper rows keep
working: a NULL ``leverage`` is treated as 1 (no margin), a NULL ``position_mode``
defaults to ``one_way``, a NULL ``time_in_force`` defaults to ``GTC``. Each
column addition is idempotent (add only when absent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # --- paper_positions ---
    if "paper_positions" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_positions")}
        if "position_side" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("position_side", sa.String(8), nullable=True),
            )
        if "leverage" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("leverage", sa.Numeric(6, 2), nullable=True),
            )
        if "margin" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("margin", sa.Numeric(24, 10), nullable=True),
            )
        if "liquidation_price" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("liquidation_price", sa.Numeric(24, 10), nullable=True),
            )
        if "mark_price" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("mark_price", sa.Numeric(24, 10), nullable=True),
            )
        if "last_funding_ts" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("last_funding_ts", sa.DateTime(timezone=True), nullable=True),
            )
        if "last_funding_rate" not in cols:
            op.add_column(
                "paper_positions",
                sa.Column("last_funding_rate", sa.Numeric(12, 10), nullable=True),
            )

    # --- paper_accounts ---
    if "paper_accounts" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_accounts")}
        if "position_mode" not in cols:
            op.add_column(
                "paper_accounts",
                sa.Column("position_mode", sa.String(8), nullable=False, server_default="one_way"),
            )
        if "margin_mode" not in cols:
            op.add_column(
                "paper_accounts",
                sa.Column("margin_mode", sa.String(8), nullable=False, server_default="cross"),
            )

    # --- paper_orders ---
    if "paper_orders" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_orders")}
        if "time_in_force" not in cols:
            op.add_column(
                "paper_orders",
                sa.Column("time_in_force", sa.String(8), nullable=False, server_default="GTC"),
            )
        if "reduce_only" not in cols:
            op.add_column(
                "paper_orders",
                sa.Column("reduce_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "post_only" not in cols:
            op.add_column(
                "paper_orders",
                sa.Column("post_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "linked_order_id" not in cols:
            op.add_column(
                "paper_orders",
                sa.Column("linked_order_id", sa.Integer(), nullable=True),
            )
        if "position_side" not in cols:
            op.add_column(
                "paper_orders",
                sa.Column("position_side", sa.String(8), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "paper_orders" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_orders")}
        for col in ("position_side", "linked_order_id", "post_only", "reduce_only", "time_in_force"):
            if col in cols:
                op.drop_column("paper_orders", col)

    if "paper_accounts" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_accounts")}
        for col in ("margin_mode", "position_mode"):
            if col in cols:
                op.drop_column("paper_accounts", col)

    if "paper_positions" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("paper_positions")}
        for col in ("last_funding_rate", "last_funding_ts", "mark_price", "liquidation_price", "margin", "leverage", "position_side"):
            if col in cols:
                op.drop_column("paper_positions", col)