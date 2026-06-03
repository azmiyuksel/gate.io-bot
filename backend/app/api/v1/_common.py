"""Shared helpers for the backtest and walk-forward endpoints."""
from __future__ import annotations

from contextlib import contextmanager

from fastapi import HTTPException

from app.core.config import get_settings


def check_csv_size(csv_data: str) -> None:
    """Reject inline CSV uploads above the configured byte cap (HTTP 413)."""
    limit = get_settings().max_csv_upload_bytes
    if len(csv_data.encode("utf-8")) > limit:
        raise HTTPException(
            status_code=413, detail=f"csv_data exceeds the {limit // (1024 * 1024)} MB limit"
        )


@contextmanager
def mark_run_failed_on_error(db, run, failed_status, invalid_detail: str = "Invalid request"):
    """Mark a backtest/walk-forward run as failed on error.

    Re-raises client HTTPExceptions as-is; wraps unexpected errors as HTTP 400
    with the message. Shared by both endpoints to remove duplicated handling.
    """
    try:
        yield
    except HTTPException:
        run.status = failed_status
        run.error = invalid_detail
        db.commit()
        raise
    except Exception as exc:
        run.status = failed_status
        run.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
