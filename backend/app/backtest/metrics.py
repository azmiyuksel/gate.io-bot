import math

import numpy as np
import pandas as pd

from app.backtest.models import BacktestTradeResult


def compute_metrics(equity_curve: list[dict], trades: list[BacktestTradeResult]) -> dict:
    if not equity_curve:
        return {}
    equity = pd.Series([point["equity"] for point in equity_curve], dtype="float64")
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1 if equity.iloc[0] else 0
    periods = max(len(equity), 1)
    annual_factor = 365 * 24
    annualized_return = (1 + total_return) ** (annual_factor / periods) - 1 if total_return > -1 else -1
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max.replace(0, np.nan)
    trade_pnls = np.array([trade.pnl for trade in trades], dtype="float64")
    wins = trade_pnls[trade_pnls > 0]
    losses = trade_pnls[trade_pnls < 0]
    downside = returns[returns < 0]
    sharpe = _ratio(returns.mean(), returns.std()) * math.sqrt(annual_factor)
    sortino = _ratio(returns.mean(), downside.std()) * math.sqrt(annual_factor)
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
        "profit_factor": float(gross_profit / gross_loss if gross_loss else gross_profit),
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


def monte_carlo(trades: list[BacktestTradeResult], initial_cash: float, scenarios: int = 1000) -> dict:
    pnls = np.array([trade.pnl for trade in trades], dtype="float64")
    if pnls.size == 0:
        return {"scenarios": scenarios, "worst_case": 0, "best_case": 0, "median_return": 0, "ruin_probability": 0}
    final_returns = []
    ruin_count = 0
    ruin_level = initial_cash * 0.5
    rng = np.random.default_rng(42)
    for _ in range(scenarios):
        sampled = rng.choice(pnls, size=pnls.size, replace=True)
        path = initial_cash + sampled.cumsum()
        final_returns.append((path[-1] / initial_cash) - 1)
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
