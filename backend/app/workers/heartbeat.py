"""Worker liveness heartbeat + watchdog helpers.

The live scheduler writes a heartbeat row every cycle. A *separate* process (the
API server) reads it and alerts when it goes stale, so a silently crashed or
stuck worker — which would leave open positions unmanaged — is detected and
surfaced instead of failing quietly.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.entities import WorkerHeartbeat

DEFAULT_WORKER = "scheduler"


def record_heartbeat(
    db: Session, worker: str = DEFAULT_WORKER, status: str = "ok", detail: str | None = None
) -> None:
    """Upsert the worker's heartbeat with the current time. Commits its own tx."""
    row = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker == worker).one_or_none()
    now = datetime.now(UTC)
    # Keep detail bounded so a long traceback can't bloat the row.
    detail = (detail or None) if detail is None else detail[:500]
    if row is None:
        db.add(WorkerHeartbeat(worker=worker, last_beat_at=now, status=status, detail=detail))
    else:
        row.last_beat_at = now
        row.status = status
        row.detail = detail
    db.commit()


def heartbeat_age_seconds(db: Session, worker: str = DEFAULT_WORKER) -> float | None:
    """Seconds since the worker last beat, or None if it has never beat."""
    row = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker == worker).one_or_none()
    if row is None or row.last_beat_at is None:
        return None
    beat = row.last_beat_at
    if beat.tzinfo is None:
        beat = beat.replace(tzinfo=UTC)
    return (datetime.now(UTC) - beat).total_seconds()


def is_stale(age_seconds: float | None, stale_threshold_seconds: float) -> bool:
    """A missing heartbeat (None) or one older than the threshold is stale."""
    return age_seconds is None or age_seconds > stale_threshold_seconds
