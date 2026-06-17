"""Tests for the go-live walk-forward validation gate."""
from datetime import UTC, datetime, timedelta

from app.models.entities import WalkForwardRun
from app.models.enums import WalkForwardStatus
from app.services.strategy.validation import live_strategy_validated

STRAT = "momentum_breakout_v1"
TF = "15m"


def _run(db, *, status=WalkForwardStatus.completed, approved=True, age_days=1,
         strategy=STRAT, timeframe=TF) -> WalkForwardRun:
    completed = datetime.now(UTC) - timedelta(days=age_days)
    run = WalkForwardRun(
        strategy_name=strategy,
        symbol="BTC_USDT",
        timeframe=timeframe,
        start_at=completed - timedelta(days=400),
        end_at=completed,
        status=status,
        deployment_decision={"approved": approved, "decision": "REQUIRES_HUMAN_REVIEW"},
        completed_at=completed,
    )
    db.add(run)
    db.commit()
    return run


def test_no_run_is_not_validated(db_session) -> None:
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False
    assert "no completed walk-forward" in result.reason


def test_passing_fresh_run_validates(db_session) -> None:
    run = _run(db_session)
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is True
    assert result.run_id == run.id


def test_unapproved_run_is_not_validated(db_session) -> None:
    _run(db_session, approved=False)
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False
    assert "did not pass" in result.reason


def test_stale_run_is_not_validated(db_session) -> None:
    _run(db_session, age_days=120)
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False
    assert "stale" in result.reason


def test_wrong_timeframe_is_not_validated(db_session) -> None:
    # A passing run on 1h must not validate a 15m live strategy.
    _run(db_session, timeframe="1h")
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False


def test_incomplete_run_is_ignored(db_session) -> None:
    _run(db_session, status=WalkForwardStatus.running)
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False


def test_latest_completed_run_wins(db_session) -> None:
    # An older passing run plus a newer failing run => latest (failing) decides.
    _run(db_session, approved=True, age_days=30)
    _run(db_session, approved=False, age_days=1)
    result = live_strategy_validated(db_session, STRAT, TF, 90)
    assert result.ok is False


def test_zero_max_age_disables_staleness(db_session) -> None:
    _run(db_session, age_days=9999)
    result = live_strategy_validated(db_session, STRAT, TF, 0)
    assert result.ok is True
