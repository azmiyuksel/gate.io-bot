"""paper_accounts.name UNIQUE constraint

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-23 12:00:00.000000

``_get_or_create_account`` (API + worker) does a SELECT-then-INSERT with no
uniqueness guarantee, so two concurrent first-requests can create two
"default" accounts — the dashboard then reads one while the worker trades the
other. This migration makes ``name`` UNIQUE.

Defensive: if duplicate "default" accounts already exist (from the race), the
oldest one (lowest id) is kept and every dependent row (orders, positions,
trades, equity_curve, logs) is reparented to it before the duplicates are
dropped. If a UNIQUE constraint is already present (e.g. applied manually), the
migration is a no-op. Idempotent across re-runs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Child tables that reference paper_accounts via account_id. They all use
# ONDELETE CASCADE, so reparenting (pointing them at the keeper) must run
# BEFORE the duplicate accounts are deleted, or their rows would cascade-delete.
_CHILD_TABLES = (
    "paper_orders",
    "paper_positions",
    "paper_trades",
    "paper_equity_curve",
    "paper_logs",
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Only operate if the paper_accounts table exists on this DB.
    if "paper_accounts" not in inspector.get_table_names():
        return

    # Deduplicate accounts that share a name: keep the oldest (lowest id) per
    # name and reparent all dependent rows onto it. This runs unconditionally
    # (cheap when there are no duplicates) so the UNIQUE constraint below can
    # never fail on pre-existing duplicates.
    names = conn.execute(sa.text("SELECT DISTINCT name FROM paper_accounts")).fetchall()
    for (name,) in names:
        rows = conn.execute(
            sa.text("SELECT id FROM paper_accounts WHERE name = :n ORDER BY id ASC"),
            {"n": name},
        ).fetchall()
        if len(rows) <= 1:
            continue
        keeper_id = rows[0][0]
        for dup_id in [r[0] for r in rows[1:]]:
            for child in _CHILD_TABLES:
                if child not in inspector.get_table_names():
                    continue
                conn.execute(
                    sa.text(
                        f"UPDATE {child} SET account_id = :keeper WHERE account_id = :dup"  # noqa: S608
                    ),
                    {"keeper": keeper_id, "dup": dup_id},
                )
            conn.execute(
                sa.text("DELETE FROM paper_accounts WHERE id = :dup"),
                {"dup": dup_id},
            )

    # Add the UNIQUE constraint only if no such constraint/index exists yet.
    existing_indexes = inspector.get_indexes("paper_accounts")
    existing_uniques = {
        ix["name"] for ix in existing_indexes if ix.get("unique") is True
    }
    # Postgres reports the constraint name via get_indexes; also check uq via
    # get_unique_constraints for completeness.
    try:
        uqs = inspector.get_unique_constraints("paper_accounts")
        existing_uniques |= {uq["name"] for uq in uqs}
    except Exception:
        pass

    if "uq_paper_accounts_name" not in existing_uniques:
        op.create_unique_constraint("uq_paper_accounts_name", "paper_accounts", ["name"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "paper_accounts" not in inspector.get_table_names():
        return
    existing = {ix["name"] for ix in inspector.get_indexes("paper_accounts")}
    try:
        existing |= {uq["name"] for uq in inspector.get_unique_constraints("paper_accounts")}
    except Exception:
        pass
    if "uq_paper_accounts_name" in existing:
        op.drop_constraint("uq_paper_accounts_name", "paper_accounts", type_="unique")
