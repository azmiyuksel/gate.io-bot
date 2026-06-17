"""Tests for the live-worker heartbeat + watchdog."""
from datetime import UTC, datetime, timedelta

from app.models.entities import WorkerHeartbeat
from app.workers.heartbeat import (
    heartbeat_age_seconds,
    is_stale,
    record_heartbeat,
)
from app.workers.watchdog import next_alert_event


def test_record_heartbeat_upserts_single_row(db_session) -> None:
    record_heartbeat(db_session, "scheduler", "ok")
    record_heartbeat(db_session, "scheduler", "error", "boom")
    rows = db_session.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker == "scheduler").all()
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert rows[0].detail == "boom"


def test_heartbeat_age_none_when_absent(db_session) -> None:
    assert heartbeat_age_seconds(db_session, "scheduler") is None


def test_heartbeat_age_is_recent_after_record(db_session) -> None:
    record_heartbeat(db_session, "scheduler", "ok")
    age = heartbeat_age_seconds(db_session, "scheduler")
    assert age is not None and 0 <= age < 5


def test_heartbeat_detail_is_truncated(db_session) -> None:
    record_heartbeat(db_session, "scheduler", "error", "x" * 1000)
    row = db_session.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker == "scheduler").one()
    assert len(row.detail) == 500


def test_is_stale_treats_missing_as_stale() -> None:
    assert is_stale(None, 2700) is True
    assert is_stale(100, 2700) is False
    assert is_stale(3000, 2700) is True


def test_stale_age_detected(db_session) -> None:
    record_heartbeat(db_session, "scheduler", "ok")
    row = db_session.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker == "scheduler").one()
    row.last_beat_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    age = heartbeat_age_seconds(db_session, "scheduler")
    assert age is not None and age > 3000


def test_watchdog_primes_silently_on_first_observation() -> None:
    # was_stale=None => baseline, no alert regardless of state.
    assert next_alert_event(None, 2700, None) == (True, None)
    assert next_alert_event(10, 2700, None) == (False, None)


def test_watchdog_alerts_down_on_healthy_to_stale() -> None:
    assert next_alert_event(3000, 2700, False) == (True, "down")
    # Missing heartbeat after being healthy is also "down".
    assert next_alert_event(None, 2700, False) == (True, "down")


def test_watchdog_alerts_recovered_on_stale_to_healthy() -> None:
    assert next_alert_event(10, 2700, True) == (False, "recovered")


def test_watchdog_silent_when_state_unchanged() -> None:
    assert next_alert_event(10, 2700, False) == (False, None)
    assert next_alert_event(3000, 2700, True) == (True, None)
