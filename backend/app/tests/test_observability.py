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


def test_trailing_stop_uses_configured_pct(db_session):
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
    engine._update_trailing_stop(position, Decimal("120"))
    # new stop = 120 * (1 - 0.05) = 114
    assert position.stop_loss == Decimal("114.00")


def test_trailing_stop_clamps_invalid_pct(db_session):
    db_session.add(StrategySettings(name="capital_preservation_v1", trailing_stop_pct=Decimal("1.5")))
    db_session.commit()
    engine = TradingEngine(db_session, client=None)
    # Invalid (>=1) pct falls back to the 1% default.
    assert engine._trailing_stop_pct() == Decimal("0.01")
