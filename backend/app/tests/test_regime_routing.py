"""Regime-aware strategy routing + the regime-filter timeframe fix."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.core.config import Settings
from app.models.enums import MarketRegimeType
from app.services.strategy.router import route_strategy_name


def _settings(**over):
    base = dict(environment="local", secret_key="t", fernet_key="t", trading_symbols="BTC_USDT")
    base.update(over)
    return Settings(**base)


def test_router_maps_trend_to_momentum_and_range_to_reversion():
    assert route_strategy_name(MarketRegimeType.trending_bull, "x") == "momentum_breakout_v1"
    assert route_strategy_name(MarketRegimeType.trending_bear, "x") == "momentum_breakout_v1"
    assert route_strategy_name(MarketRegimeType.breakout_phase, "x") == "momentum_breakout_v1"
    assert route_strategy_name(MarketRegimeType.high_volatility, "x") == "momentum_breakout_v1"
    assert route_strategy_name(MarketRegimeType.sideways, "x") == "capital_preservation_v1"
    assert route_strategy_name(MarketRegimeType.low_volatility, "x") == "capital_preservation_v1"


def test_resolve_strategy_off_by_default(db_session):
    from app.services.trading_engine import TradingEngine

    with patch("app.services.trading_engine.get_settings", return_value=_settings(regime_routing_enabled=False)):
        engine = TradingEngine(db_session, AsyncMock())
        strat, pre = engine._resolve_strategy("BTC_USDT", [])
    assert strat is engine.strategy
    assert pre is False


def test_resolve_strategy_routes_range_to_reversion(db_session):
    """With routing on and a (fallback) SIDEWAYS regime, the engine routes the
    default momentum strategy to the mean-reversion strategy."""
    from app.services.trading_engine import TradingEngine

    # A short candle list -> update_regime takes the <210 fallback => SIDEWAYS.
    candles_list = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0, "timestamp": i}
        for i in range(5)
    ]
    with patch("app.services.trading_engine.get_settings",
               return_value=_settings(regime_routing_enabled=True, market_data_interval="15m")):
        engine = TradingEngine(db_session, AsyncMock())
        assert engine.strategy.name == "momentum_breakout_v1"
        strat, pre = engine._resolve_strategy("BTC_USDT", candles_list)
    assert strat.name == "capital_preservation_v1"
    assert pre is True


def test_regime_filter_reads_and_writes_same_timeframe(db_session):
    """The regime filter must call should_trade with the SAME timeframe it wrote
    (market_data_interval), not the old hardcoded "1h" default that made it
    always see a fallback SIDEWAYS regime and block every breakout strategy."""
    from app.services.trading_engine import TradingEngine

    seen = {}

    class _FakeRegime:
        def __init__(self, db):
            pass

        def update_regime(self, symbol, timeframe, candles_list):
            seen["update_tf"] = timeframe

        def should_trade(self, strategy_name, symbol, timeframe="1h"):
            seen["should_trade_tf"] = timeframe
            return True, "allowed", Decimal("1")

    with patch("app.services.trading_engine.get_settings", return_value=_settings(market_data_interval="15m")), \
         patch("app.services.trading_engine.MarketRegimeEngine", _FakeRegime):
        engine = TradingEngine(db_session, AsyncMock())
        allowed, _, _ = engine._check_regime_filter("BTC_USDT", [], "momentum_breakout_v1")

    assert allowed is True
    assert seen["update_tf"] == "15m"
    assert seen["should_trade_tf"] == "15m"


def test_paper_adapter_routes_by_regime():
    from app.paper_trading.strategy_adapter import CapitalPreservationAdapter

    with patch("app.paper_trading.strategy_adapter.get_settings", return_value=_settings(paper_strategy="momentum_breakout_v1")):
        adapter = CapitalPreservationAdapter()
        assert adapter.route_for_regime(MarketRegimeType.sideways) == "capital_preservation_v1"
        assert adapter._strategy.name == "capital_preservation_v1"
        assert adapter.route_for_regime(MarketRegimeType.trending_bull) == "momentum_breakout_v1"
        assert adapter._strategy.name == "momentum_breakout_v1"
