"""add paper_positions.side and paper_trades.exit_reason

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-20 13:00:00.000000

Closes a schema drift: the ``PaperPosition.side`` and ``PaperTrade.exit_reason``
columns exist in the models but were never created by any Alembic migration —
they had only been bolted onto the deployed DB by an out-of-band ad-hoc script
(``scripts/migrate_railway.py``, now removed because it hardcoded a live DB
password). A fresh DB built purely from migrations was therefore missing them.

Idempotent across environments: the deployed Postgres already has both columns
(from the ad-hoc script), while a fresh/test DB does not — so each column is
added only when absent (checked via the runtime inspector) rather than failing
with "column already exists" on the existing deployment.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    paper_positions_cols = {c["name"] for c in inspector.get_columns("paper_positions")}
    if "side" not in paper_positions_cols:
        # NOT NULL with a server default so the ALTER backfills existing rows.
        op.add_column(
            "paper_positions",
            sa.Column("side", sa.String(length=8), nullable=False, server_default="buy"),
        )

    paper_trades_cols = {c["name"] for c in inspector.get_columns("paper_trades")}
    if "exit_reason" not in paper_trades_cols:
        op.add_column(
            "paper_trades",
            sa.Column("exit_reason", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    paper_trades_cols = {c["name"] for c in inspector.get_columns("paper_trades")}
    if "exit_reason" in paper_trades_cols:
        op.drop_column("paper_trades", "exit_reason")

    paper_positions_cols = {c["name"] for c in inspector.get_columns("paper_positions")}
    if "side" in paper_positions_cols:
        op.drop_column("paper_positions", "side")
