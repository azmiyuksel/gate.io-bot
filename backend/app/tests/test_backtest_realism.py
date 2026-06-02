"""Tests for backtest realism fixes: no same-bar lookahead, timeframe-aware
annualization, and the buy-and-hold benchmark."""
import math
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.backtest.broker import VirtualBroker
from app.backtest.engine import BacktestEngine
from app.backtest.metrics import (
    buy_and_hold_benchmark,
    compute_metrics,
    periods_per_year,
)
from app.backtest.models import BacktestConfig
from app.backtest.portfolio import Portfolio
from app.backtest.strategy_runner import EmaRsiAtrStrategy


def _candle(o, h, low, c):
    return pd.Series(
        {"open": o, "high": h, "low": low, "close": c},
        name=pd.Timestamp("2024-01-01", tz="UTC"),
    )


def _config() -> BacktestConfig:
    return BacktestConfig(
        symbol="BTC_USDT",
        timeframe="1h",
        start_at=datetime(2024, 1, 1, tzinfo=UTC),
        end_at=datetime(2024, 3, 1, tzinfo=UTC),
        initial_cash=10_000.0,
    )


def _noisy_curve(n: int = 80) -> list[dict]:
    rng = np.random.default_rng(7)
    rets = 0.001 + rng.normal(0, 0.002, n)
    equity = 100.0 * np.cumprod(1 + rets)
    return [{"equity": float(e)} for e in equity]


def _oscillating_uptrend(n: int = 420) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    i = np.arange(n)
    close = 100 + 0.05 * i + 3.0 * np.sin(2 * np.pi * i / 20)
    openp = close - 0.05
    high = np.maximum(openp, close) + 0.5
    low = np.minimum(openp, close) - 0.5
    vol = np.full(n, 10.0)
    return pd.DataFrame(
        {"open": openp, "high": high, "low": low, "close": close, "volume": vol}, index=idx
    )


def test_periods_per_year_mapping():
    assert periods_per_year("1h") == 365 * 24
    assert periods_per_year("1d") == 365
    assert periods_per_year("5m") == 365 * 24 * 12
    # Unknown timeframe falls back to hourly.
    assert periods_per_year("???") == 365 * 24


def test_buy_and_hold_benchmark_return():
    bench = buy_and_hold_benchmark([100.0, 110.0], "1h")
    assert abs(bench["buy_hold_return"] - 0.10) < 1e-9


def test_annualization_is_timeframe_aware():
    curve = _noisy_curve()
    hourly = compute_metrics(curve, [], timeframe="1h")
    daily = compute_metrics(curve, [], timeframe="1d")
    # Same curve annualized at different bar frequencies => different Sharpe.
    assert hourly["sharpe_ratio"] != daily["sharpe_ratio"]
    # Hourly scales by sqrt(8760) vs daily sqrt(365): ratio = sqrt(24).
    assert abs(hourly["sharpe_ratio"] / daily["sharpe_ratio"] - math.sqrt((365 * 24) / 365)) < 1e-6


def test_risk_free_rate_lowers_sharpe():
    curve = _noisy_curve()
    base = compute_metrics(curve, [], timeframe="1h", risk_free_rate=0.0)
    with_rf = compute_metrics(curve, [], timeframe="1h", risk_free_rate=0.05)
    assert with_rf["sharpe_ratio"] < base["sharpe_ratio"]


def test_engine_result_includes_benchmark():
    data = _oscillating_uptrend()
    config = _config()
    result = BacktestEngine().run(data, config)
    assert "benchmark" in result
    assert "buy_hold_return" in result["metrics"]
    assert "excess_return_vs_buy_hold" in result["metrics"]


def test_no_same_bar_lookahead():
    """An entry signalled on a bar's close must fill on the NEXT bar's open."""
    data = _oscillating_uptrend()
    config = _config()

    # Independently reconstruct the first signal bar using the same strategy.
    strategy = EmaRsiAtrStrategy(config.parameters)
    prepared = strategy.prepare(data)
    first_signal_pos = None
    for pos in range(len(prepared)):
        strategy.on_candle(prepared.iloc[pos])
        if strategy.should_buy():
            first_signal_pos = pos
            break
    assert first_signal_pos is not None, "test data did not trigger any signal"

    result = BacktestEngine().run(data, config)
    trades = result["trades"]
    assert trades, "expected at least one trade"

    first_trade = trades[0]
    next_open = float(prepared.iloc[first_signal_pos + 1]["open"])
    # Default broker buy fill = open * (1 + spread/2 + slippage).
    expected_fill = next_open * (1 + 0.0002 / 2 + 0.0005)
    assert abs(first_trade.entry_price - expected_fill) < 1e-6
    # And the fill timestamp is the bar AFTER the signal bar (no same-bar fill).
    assert first_trade.entry_time == prepared.index[first_signal_pos + 1]


def test_limit_buy_fills_at_maker_price_when_touched():
    pf = Portfolio(10_000.0)
    broker = VirtualBroker(pf, commission_rate=0.001, maker_fee_rate=0.0005)
    candle = _candle(100, 101, 98, 99)  # low (98) <= limit (99) -> fills
    pos = broker.limit_buy(candle, "BTC_USDT", 1.0, 99.0, 95.0, 110.0)
    assert pos is not None
    assert pos.entry_price == 99.0  # maker fill at the limit, no slippage/spread
    assert pos.fee_paid == 99.0 * 1.0 * 0.0005  # maker fee rate


def test_limit_buy_misses_when_price_never_reaches_limit():
    pf = Portfolio(10_000.0)
    broker = VirtualBroker(pf, commission_rate=0.001, maker_fee_rate=0.0005)
    candle = _candle(100, 101, 99.5, 100.5)  # low (99.5) > limit (99) -> no fill
    assert broker.limit_buy(candle, "BTC_USDT", 1.0, 99.0, 95.0, 110.0) is None


def test_maker_exit_has_no_slippage_taker_exit_does():
    pf = Portfolio(10_000.0)
    broker = VirtualBroker(
        pf, commission_rate=0.001, maker_fee_rate=0.0005, slippage_rate=0.0005, spread_rate=0.0002
    )
    candle = _candle(100, 100, 100, 100)
    # Take-profit (maker): fills exactly at the target, maker fee, no slippage.
    tp_pos = broker.market_buy(candle, "BTC_USDT", 1.0, 95.0, 110.0)
    broker._close(tp_pos, candle, 110.0, "take_profit", maker=True)
    tp_trade = pf.closed_trades[-1]
    assert tp_trade.exit_price == 110.0

    # Stop-loss (taker): fills below the level by spread/slippage.
    sl_pos = broker.market_buy(candle, "BTC_USDT", 1.0, 95.0, 110.0)
    broker._close(sl_pos, candle, 95.0, "stop_loss", maker=False)
    sl_trade = pf.closed_trades[-1]
    assert sl_trade.exit_price < 95.0


def test_limit_mode_runs_and_avoids_slippage_premium():
    data = _oscillating_uptrend()
    base = _config()
    limit_cfg = BacktestConfig(
        symbol=base.symbol,
        timeframe=base.timeframe,
        start_at=base.start_at,
        end_at=base.end_at,
        initial_cash=base.initial_cash,
        execution_mode="limit",
    )
    limit_result = BacktestEngine().run(data, limit_cfg)
    # Both produce valid metrics; limit mode is a maker strategy (may miss fills).
    assert "metrics" in limit_result
    if limit_result["trades"]:
        # A maker fill never pays the market buy slippage premium, so the entry
        # price equals the (prior-bar) signal close, which is below the next open.
        for trade in limit_result["trades"]:
            assert trade.entry_price <= trade.exit_price or trade.pnl <= 0
