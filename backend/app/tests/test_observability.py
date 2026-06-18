"""Tests for the observability middleware and configurable risk params."""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.entities import Position, StrategySettings
from app.models.enums import PositionStatus
from app.services.trading_engine import TradingEngine


def test_health_sets_correlation_header():
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID")


def test_incoming_request_id_is_echoed():
    client = TestClient(app)
    res = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert res.headers.get("X-Request-ID") == "abc123"


def test_metrics_endpoint_exposes_prometheus():
    client = TestClient(app)
    client.get("/health")  # generate at least one sample
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "http_requests_total" in res.text


async def test_trailing_stop_uses_configured_pct(db_session, monkeypatch):
    # 5% trailing stop configured in StrategySettings.
    db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("0.05")))
    position = Position(
        symbol="BTC_USDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
        status=PositionStatus.open,
    )
    db_session.add(position)
    db_session.commit()

    engine = TradingEngine(db_session, client=None)
    # Trailing stop now amends the resting exchange stop; stub it out so the
    # unit test stays focused on the % math without a live exchange client.
    from unittest.mock import AsyncMock

    monkeypatch.setattr(engine, "_amend_exchange_stop", AsyncMock())
    await engine._update_trailing_stop(position, Decimal("120"))
    # new stop = 120 * (1 - 0.05) = 114
    assert position.stop_loss == Decimal("114.00")


async def test_chandelier_trailing_uses_atr_distance(db_session, monkeypatch):
    """When chandelier_trailing_enabled and ATR is provided, the trailing
    distance is ATR * chandelier_atr_mult (volatility-adaptive), not a fixed %.
    At ATR=6, mult=3 -> distance=18; stop = 120 - 18 = 102 (vs fixed 5% -> 114)."""
    from app.core.config import get_settings

    db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("0.05")))
    position = Position(
        symbol="BTC_USDT",
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
        status=PositionStatus.open,
    )
    db_session.add(position)
    db_session.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "chandelier_trailing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "chandelier_atr_mult", 3.0, raising=False)

    engine = TradingEngine(db_session, client=None)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(engine, "_amend_exchange_stop", AsyncMock())
    # ATR=6, price=120 -> distance = 6*3 = 18 -> stop = 120*(1 - 18/120) = 102.
    await engine._update_trailing_stop(position, Decimal("120"), atr_value=Decimal("6"))
    assert position.stop_loss == Decimal("102")


async def test_chandelier_falls_back_to_pct_when_atr_missing(db_session, monkeypatch):
    """No ATR provided -> falls back to the fixed-% trailing (legacy behavior)."""
    from app.core.config import get_settings

    db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("0.05")))
    position = Position(
        symbol="BTC_USDT", entry_price=Decimal("100"), quantity=Decimal("1"),
        stop_loss=Decimal("90"), take_profit=Decimal("130"), status=PositionStatus.open,
    )
    db_session.add(position)
    db_session.commit()

    settings = get_settings()
    monkeypatch.setattr(settings, "chandelier_trailing_enabled", True, raising=False)
    monkeypatch.setattr(settings, "chandelier_atr_mult", 3.0, raising=False)

    engine = TradingEngine(db_session, client=None)
    from unittest.mock import AsyncMock

    monkeypatch.setattr(engine, "_amend_exchange_stop", AsyncMock())
    await engine._update_trailing_stop(position, Decimal("120"), atr_value=None)
    # Falls back to 5% -> 120 * 0.95 = 114.
    assert position.stop_loss == Decimal("114.00")


def test_trailing_stop_clamps_invalid_pct(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    # The CHECK constraint now prevents storing invalid trailing_stop_pct (>=1).
    with pytest.raises(IntegrityError):
        db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("1.5")))
        db_session.commit()
    db_session.rollback()
    # Valid edge-case: code-level clamping still works as defense-in-depth.
    db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("0.01")))
    db_session.commit()
    engine = TradingEngine(db_session, client=None)
    assert engine._trailing_stop_pct() == Decimal("0.01")
