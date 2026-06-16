"""add paper-trading composite performance indexes

Revision ID: c1f2a3b4d5e6
Revises: b8d5e3f6a1c9
Create Date: 2026-06-16 12:45:00.000000

The paper dashboard and the trade worker repeatedly filter these tables by
account_id (an unindexed FK) and order/range by a time/flag column. As the
equity-curve (5-min cadence) and log tables grow, those queries degrade to
sequential scans, slowing both the dashboard and the worker's per-cycle risk
checks. These composite indexes match the exact access patterns.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c1f2a3b4d5e6'
down_revision: Union[str, None] = 'b8d5e3f6a1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_paper_trades_account_traded', 'paper_trades',
        ['account_id', 'traded_at'], unique=False,
    )
    op.create_index(
        'ix_paper_positions_account_open', 'paper_positions',
        ['account_id', 'is_open'], unique=False,
    )
    op.create_index(
        'ix_paper_equity_account_ts', 'paper_equity_curve',
        ['account_id', 'timestamp'], unique=False,
    )
    op.create_index(
        'ix_paper_logs_account_event_created', 'paper_logs',
        ['account_id', 'event', 'created_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_paper_logs_account_event_created', table_name='paper_logs')
    op.drop_index('ix_paper_equity_account_ts', table_name='paper_equity_curve')
    op.drop_index('ix_paper_positions_account_open', table_name='paper_positions')
    op.drop_index('ix_paper_trades_account_traded', table_name='paper_trades')
