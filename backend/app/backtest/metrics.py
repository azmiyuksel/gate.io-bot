import math

import numpy as np
import pandas as pd

from app.backtest.models import BacktestTradeResult

# Number of bars in a calendar year per timeframe; used to annualize returns and
# risk ratios correctly instead of assuming hourly data.
_BARS_PER_YEAR = {
    "1m": 365 * 24 * 60,
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "1h": 365 * 24,
    "4h": 365 * 6,
    "1d": 365,
}


def periods_per_year(timeframe: str) -> int:
    return _BARS_PER_YEAR.get(timeframe, 365 * 24)


def compute_metrics(
    equity_curve: list[dict],
    trades: list[BacktestTradeResult],
    timeframe: str = "1h",
    risk_free_rate: float = 0.0,
) -> dict:
    if not equity_curve:
        return {}
    equity = pd.Series([point["equity"] for point in equity_curve], dtype="float64")
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1 if equity.iloc[0] else 0
    periods = max(len(equity), 1)
    # Annualization factor follows the actual bar frequency, not a fixed 1h assumption.
    annual_factor = periods_per_year(timeframe)
    annualized_return = (1 + total_return) ** (annual_factor / periods) - 1 if total_return > -1 else -1
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max.replace(0, np.nan)
    trade_pnls = np.array([trade.pnl for trade in trades], dtype="float64")
    wins = trade_pnls[trade_pnls > 0]
    losses = trade_pnls[trade_pnls < 0]
    downside = returns[returns < 0]
    # Subtract the per-bar risk-free rate so Sharpe/Sortino measure excess return.
    rf_per_period = risk_free_rate / annual_factor
    excess = returns.mean() - rf_per_period
    sharpe = _ratio(excess, returns.std()) * math.sqrt(annual_factor)
    sortino = _ratio(excess, downside.std()) * math.sqrt(annual_factor)
    calmar = _ratio(annualized_return, abs(drawdown.min()))
    gross_profit = wins.sum() if wins.size else 0
    gross_loss = abs(losses.sum()) if losses.size else 0
    return {
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "cagr": float(annualized_return),
        "max_drawdown": float(drawdown.min() if len(drawdown) else 0),
        "average_drawdown": float(drawdown[drawdown < 0].mean() if (drawdown < 0).any() else 0),
        "drawdown_duration": int(_max_drawdown_duration(drawdown)),
        "win_rate": float(len(wins) / len(trade_pnls) if len(trade_pnls) else 0),
        "profit_factor": float(min(gross_profit / gross_loss, 5.0) if gross_loss else min(gross_profit, 5.0)),
        "expectancy": float(trade_pnls.mean() if len(trade_pnls) else 0),
        "average_trade": float(trade_pnls.mean() if len(trade_pnls) else 0),
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "calmar_ratio": float(calmar),
        "total_trades": int(len(trades)),
        "long_trades": int(len(trades)),
        "winning_trades": int(len(wins)),
        "losing_trades": int(len(losses)),
        "net_profit": float(equity.iloc[-1] - equity.iloc[0]),
    }


def buy_and_hold_benchmark(closes: list[float], timeframe: str = "1h") -> dict:
    """Buy-and-hold the asset over the same window — the honest baseline.

    A strategy only adds value if it beats simply holding the asset on a
    risk-adjusted basis, so we report the benchmark return/Sharpe alongside it.
    """
    if not closes or len(closes) < 2 or closes[0] <= 0:
        return {"buy_hold_return": 0.0, "buy_hold_sharpe": 0.0}
    series = pd.Series(closes, dtype="float64")
    bh_return = float(series.iloc[-1] / series.iloc[0] - 1)
    rets = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    annual_factor = periods_per_year(timeframe)
    bh_sharpe = float(_ratio(rets.mean(), rets.std()) * math.sqrt(annual_factor))
    return {"buy_hold_return": bh_return, "buy_hold_sharpe": bh_sharpe}


def _equity_fraction_returns(pnls: np.ndarray, initial_cash: float) -> np.ndarray:
    """Reconstruct each trade's return as a fraction of equity-before-trade.

    Bootstrapping these returns and compounding them models a %-of-equity sizing
    strategy honestly, instead of assuming a fixed absolute stake (additive PnL).
    """
    equity = initial_cash
    returns = np.empty(pnls.size)
    for i, pnl in enumerate(pnls):
        returns[i] = pnl / equity if equity > 0 else 0.0
        equity += pnl
    return returns


def monte_carlo(trades: list[BacktestTradeResult], initial_cash: float, scenarios: int = 1000) -> dict:
    pnls = np.array([trade.pnl for trade in trades], dtype="float64")
    if pnls.size == 0:
        return {"scenarios": scenarios, "worst_case": 0, "best_case": 0, "median_return": 0, "ruin_probability": 0}
    returns = _equity_fraction_returns(pnls, initial_cash)
    final_returns = []
    ruin_count = 0
    ruin_level = 0.5  # equity falling to 50% of the starting balance
    rng = np.random.default_rng(42)
    for _ in range(scenarios):
        sampled = rng.choice(returns, size=returns.size, replace=True)
        path = np.cumprod(1.0 + sampled)  # equity relative to start (starts at 1)
        final_returns.append(float(path[-1] - 1.0))
        ruin_count += int(path.min() <= ruin_level)
    return {
        "scenarios": scenarios,
        "worst_case": float(np.min(final_returns)),
        "best_case": float(np.max(final_returns)),
        "median_return": float(np.median(final_returns)),
        "ruin_probability": float(ruin_count / scenarios),
    }


def _ratio(numerator: float, denominator: float) -> float:
    if denominator is None or np.isnan(denominator) or denominator == 0:
        return 0
    return numerator / denominator


def _max_drawdown_duration(drawdown: pd.Series) -> int:
    duration = 0
    max_duration = 0
    for value in drawdown.fillna(0):
        if value < 0:
            duration += 1
            max_duration = max(max_duration, duration)
        else:
            duration = 0
    return max_duration
