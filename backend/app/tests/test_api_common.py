"""Tests for the shared backtest/walk-forward endpoint helpers."""
import pytest
from fastapi import HTTPException

from app.api.v1._common import check_csv_size, mark_run_failed_on_error


class _Run:
    def __init__(self):
        self.status = "running"
        self.error = None


class _Db:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


def test_check_csv_size_allows_small_payload():
    check_csv_size("a,b,c\n1,2,3")  # well under the cap -> no raise


def test_check_csv_size_rejects_oversized_payload():
    big = "x" * (10 * 1024 * 1024 + 1)  # just over the 10 MB default
    with pytest.raises(HTTPException) as exc:
        check_csv_size(big)
    assert exc.value.status_code == 413


def test_mark_run_failed_reraises_http_exception():
    run, db = _Run(), _Db()
    with pytest.raises(HTTPException) as exc:
        with mark_run_failed_on_error(db, run, "failed", "bad request"):
            raise HTTPException(status_code=404, detail="nope")
    assert exc.value.status_code == 404  # original error preserved
    assert run.status == "failed"
    assert run.error == "bad request"
    assert db.committed is True


def test_mark_run_failed_wraps_unexpected_error_as_400():
    run, db = _Run(), _Db()
    with pytest.raises(HTTPException) as exc:
        with mark_run_failed_on_error(db, run, "failed"):
            raise ValueError("boom")
    assert exc.value.status_code == 400
    assert "boom" in exc.value.detail
    assert run.status == "failed"
    assert run.error == "boom"


def test_mark_run_failed_passes_through_success():
    run, db = _Run(), _Db()
    with mark_run_failed_on_error(db, run, "failed"):
        pass
    assert run.status == "running"  # untouched on success
    assert db.committed is False
