"""Trade-economics analytics: does the strategy actually have an edge?

These answer the first question an economist asks — is expected value per trade
positive, and does the realized win rate clear the break-even win rate implied
by the payoff ratio (after costs, since PnL here is net of fees)?
"""
from __future__ import annotations


def trade_economics(pnls: list[float]) -> dict:
    """Edge metrics from realized (fee-net) trade PnLs.

    - expectancy: average PnL per trade (the EV).
    - payoff_ratio: average win / average loss.
    - break_even_win_rate: win rate needed just to break even given the payoff
      ratio = avg_loss / (avg_win + avg_loss).
    - edge: realized win rate minus break-even win rate (positive => profitable).
    - expectancy_r: expectancy expressed in units of average loss (R-multiple).
    """
    n = len(pnls)
    if n == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "payoff_ratio": 0.0,
            "expectancy": 0.0,
            "expectancy_r": 0.0,
            "break_even_win_rate": 0.0,
            "edge": 0.0,
            "has_edge": False,
        }
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]  # positive magnitudes
    win_rate = len(wins) / n
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    expectancy = sum(pnls) / n
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
    denom = avg_win + avg_loss
    break_even = avg_loss / denom if denom > 0 else 0.0
    edge = win_rate - break_even
    expectancy_r = expectancy / avg_loss if avg_loss > 0 else 0.0
    return {
        "trades": n,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "expectancy": expectancy,
        "expectancy_r": expectancy_r,
        "break_even_win_rate": break_even,
        "edge": edge,
        "has_edge": expectancy > 0 and edge > 0,
    }


def hurdle_comparison(
    strategy_return: float, annual_risk_free_rate: float, period_days: float
) -> dict:
    """Compare the strategy's return against the opportunity cost of idle capital.

    Idle USDT could earn a ~risk-free yield (lending/Earn); the strategy only
    creates value if it beats that hurdle over the same period.
    """
    if period_days <= 0:
        hurdle = 0.0
    else:
        hurdle = (1 + annual_risk_free_rate) ** (period_days / 365.0) - 1
    excess = strategy_return - hurdle
    return {
        "annual_risk_free_rate": annual_risk_free_rate,
        "period_days": period_days,
        "hurdle_return": hurdle,
        "excess_over_hurdle": excess,
        "beats_hurdle": excess > 0,
    }


def benchmark_comparison(strategy_return: float, benchmark_closes: list[float]) -> dict:
    """Strategy return vs buy-and-hold the benchmark asset over the same window.

    `excess_return` (alpha proxy) is the economically decisive number: a strategy
    only adds value if it beats simply holding the asset.
    """
    if len(benchmark_closes) < 2 or benchmark_closes[0] <= 0:
        return {
            "strategy_return": strategy_return,
            "benchmark_return": 0.0,
            "excess_return": strategy_return,
            "outperforms": strategy_return > 0,
        }
    benchmark_return = benchmark_closes[-1] / benchmark_closes[0] - 1
    excess = strategy_return - benchmark_return
    return {
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "excess_return": excess,
        "outperforms": excess > 0,
    }
