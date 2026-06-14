"""add timeframe column to hypothesis_tests

Revision ID: e4b7c2f91a3d
Revises: 0dedc3830d10
Create Date: 2026-06-14 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e4b7c2f91a3d"
down_revision: Union[str, None] = "0dedc3830d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hypothesis_tests",
        sa.Column("timeframe", sa.String(8), server_default="1h", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("hypothesis_tests", "timeframe")
