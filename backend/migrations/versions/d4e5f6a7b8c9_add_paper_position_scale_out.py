"""add initial_stop_loss, scaled_out to paper_positions

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-06-22 10:00:00.000000

Partial profit taking (scale-out) for the paper engine: close a fraction of
a paper position once it reaches +1R profit, then ride the remainder risk-free.
R is the INITIAL risk-per-unit, so ``initial_stop_loss`` preserves the entry
stop even after trailing/breakeven move ``stop_loss``. ``scaled_out`` ensures
the partial fires at most once. Both nullable/defaulted so pre-existing open
paper positions keep working (they simply never scale out).

Idempotent: the deployed Postgres may not have these columns yet (created by
a prior migration on fresh DBs, or missing on deployed — depends on the
migration order). Each column is added only when absent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = {c["name"] for c in inspector.get_columns("paper_positions")}

    if "initial_stop_loss" not in columns:
        op.add_column(
            "paper_positions",
            sa.Column("initial_stop_loss", sa.Numeric(24, 10), nullable=True),
        )
    if "scaled_out" not in columns:
        op.add_column(
            "paper_positions",
            sa.Column("scaled_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    op.drop_column("paper_positions", "initial_stop_loss")
    op.drop_column("paper_positions", "scaled_out")
