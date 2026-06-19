"""init_db schema-bootstrap branching.

On a DB with no alembic_version table we must distinguish a FRESH/empty DB (run
the migrations to create the schema) from a LEGACY create_all DB (stamp only).
Stamping a fresh DB would leave it with no tables — the Railway fresh-deploy bug.
"""
from unittest.mock import MagicMock, patch


class _FakeInspector:
    def __init__(self, tables):
        self._tables = set(tables)

    def has_table(self, name):
        return name in self._tables


def _run_with_tables(tables):
    """Run init_db with a fake inspector reporting `tables`, capturing the alembic
    command calls (stamp vs upgrade) without touching a real database."""
    import alembic.command as command  # ensure the submodule is importable to patch

    # Fake engine reporting a non-postgres dialect so init_db skips the advisory
    # lock (which would need a real DB connection) and runs the schema-sync logic
    # directly. inspect() is patched, so the engine is otherwise unused.
    fake_engine = MagicMock()
    fake_engine.dialect.name = "sqlite"

    with patch("sqlalchemy.inspect", return_value=_FakeInspector(tables)), \
         patch("app.db.session.engine", fake_engine), \
         patch.object(command, "stamp") as stamp, \
         patch.object(command, "upgrade") as upgrade, \
         patch("app.db.init_db._cleanup_paper_data"), \
         patch("app.db.init_db._mark_cleanup_done"), \
         patch("app.db.init_db._cleanup_if_needed"):
        from app.db.init_db import init_db

        init_db()
    return MagicMock(stamp=stamp, upgrade=upgrade)


def test_fresh_empty_db_runs_migrations():
    # No alembic_version AND no domain tables -> must UPGRADE (create schema).
    cmd = _run_with_tables(tables=set())
    cmd.upgrade.assert_called_once()
    cmd.stamp.assert_not_called()


def test_legacy_create_all_db_is_stamped():
    # No alembic_version but domain tables exist (legacy create_all) -> STAMP.
    cmd = _run_with_tables(tables={"users"})
    cmd.stamp.assert_called_once()
    cmd.upgrade.assert_not_called()


def test_tracked_db_upgrades():
    # alembic_version present -> normal UPGRADE path.
    cmd = _run_with_tables(tables={"alembic_version", "users"})
    cmd.upgrade.assert_called_once()
    cmd.stamp.assert_not_called()


def test_postgres_serializes_with_advisory_lock():
    """On postgres, init_db wraps the schema sync in a pg advisory lock so the
    API + workers don't race concurrent `upgrade head` runs at boot."""
    import alembic.command as command

    fake_engine = MagicMock()
    fake_engine.dialect.name = "postgresql"
    conn = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = conn

    with patch("sqlalchemy.inspect", return_value=_FakeInspector({"alembic_version"})), \
         patch("app.db.session.engine", fake_engine), \
         patch.object(command, "upgrade"), \
         patch.object(command, "stamp"), \
         patch("app.db.init_db._cleanup_paper_data"), \
         patch("app.db.init_db._mark_cleanup_done"), \
         patch("app.db.init_db._cleanup_if_needed"):
        from app.db.init_db import init_db

        init_db()

    calls = [str(c.args[0]) for c in conn.exec_driver_sql.call_args_list]
    assert any("pg_advisory_lock" in c for c in calls)
    assert any("pg_advisory_unlock" in c for c in calls)
