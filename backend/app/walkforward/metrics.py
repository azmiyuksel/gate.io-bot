import numpy as np


def objective_score(metrics: dict) -> float:
    sharpe = float(metrics.get("sharpe_ratio", 0))
    profit_factor = min(float(metrics.get("profit_factor", 0)), 5)
    cagr = float(metrics.get("cagr", 0))
    drawdown = abs(float(metrics.get("max_drawdown", 0)))
    total_trades = float(metrics.get("total_trades", 0))
    # Penalize strategies with very few trades — they lack statistical significance.
    trade_penalty = max(0, (20 - total_trades)) * 0.1
    return sharpe + profit_factor + cagr - drawdown - trade_penalty


def walk_forward_efficiency(train_profit: float, test_profit: float) -> float:
    if train_profit <= 0:
        return 0
    return max(test_profit / train_profit, 0)


def wfe_label(wfe: float) -> str:
    if wfe > 0.75:
        return "Excellent"
    if wfe > 0.50:
        return "Good"
    if wfe < 0.30:
        return "Overfit Risk"
    return "Weak"


def aggregate_results(window_results: list) -> dict:
    if not window_results:
        return {}
    test_metrics = [window.test_metrics for window in window_results]
    train_profit = sum(float(window.train_metrics.get("net_profit", 0)) for window in window_results)
    test_profit = sum(float(window.test_metrics.get("net_profit", 0)) for window in window_results)
    # WFE on RATE-normalized (annualized) returns, not raw profit sums: train
    # windows are far longer than test windows, so summed net profit understates
    # out-of-sample efficiency and overstates "overfit". Compare like-for-like.
    train_ann = float(np.mean([float(w.train_metrics.get("annualized_return", 0)) for w in window_results]))
    test_ann = float(np.mean([float(w.test_metrics.get("annualized_return", 0)) for w in window_results]))
    wfe = walk_forward_efficiency(train_ann, test_ann)
    positive = sum(1 for metric in test_metrics if float(metric.get("net_profit", 0)) > 0)
    consistency = positive / len(window_results)
    avg_sharpe = float(np.mean([metric.get("sharpe_ratio", 0) for metric in test_metrics]))
    avg_sortino = float(np.mean([metric.get("sortino_ratio", 0) for metric in test_metrics]))
    avg_drawdown = float(np.mean([metric.get("max_drawdown", 0) for metric in test_metrics]))
    avg_pf = float(np.mean([metric.get("profit_factor", 0) for metric in test_metrics]))
    worst_drawdown = float(np.min([metric.get("max_drawdown", 0) for metric in test_metrics]))
    best_window = max(window_results, key=lambda item: item.test_metrics.get("net_profit", 0))
    worst_window = min(window_results, key=lambda item: item.test_metrics.get("net_profit", 0))
    # True out-of-sample total return: compound each test window's return
    # (the old `test_profit/train_profit` was an efficiency ratio, not a return).
    oos_compounded = 1.0
    for metric in test_metrics:
        oos_compounded *= 1.0 + float(metric.get("total_return", 0))
    total_return = oos_compounded - 1.0
    annualized_return = float(np.mean([metric.get("annualized_return", 0) for metric in test_metrics]))
    robustness = robustness_score(consistency, wfe, avg_sharpe, worst_drawdown, avg_pf)
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "average_sharpe": avg_sharpe,
        "average_sortino": avg_sortino,
        "average_drawdown": avg_drawdown,
        "average_profit_factor": avg_pf,
        "worst_drawdown": worst_drawdown,
        "best_window": best_window.window_id,
        "worst_window": worst_window.window_id,
        "in_sample_net_profit": train_profit,
        "out_of_sample_net_profit": test_profit,
        "wfe": wfe,
        "wfe_label": wfe_label(wfe),
        "positive_windows": positive,
        "total_windows": len(window_results),
        "consistency_score": consistency,
        "robustness_score": robustness,
    }


def robustness_score(consistency: float, wfe: float, sharpe: float, drawdown: float, profit_factor: float) -> float:
    consistency_component = min(max(consistency, 0), 1) * 30
    wfe_component = min(max(wfe, 0), 1) * 25
    sharpe_component = min(max(sharpe / 2, 0), 1) * 20
    drawdown_component = max(1 - min(abs(drawdown) / 0.30, 1), 0) * 15
    pf_component = min(max(profit_factor / 2, 0), 1) * 10
    return round(consistency_component + wfe_component + sharpe_component + drawdown_component + pf_component, 2)


def monte_carlo_wfa(trades: list[dict], initial_cash: float, scenarios: int = 1000) -> dict:
    from app.backtest.metrics import _equity_fraction_returns

    pnls = np.array([trade.get("pnl", 0) for trade in trades], dtype="float64")
    if pnls.size == 0:
        return {"var_95": 0, "expected_shortfall": 0, "worst_drawdown": 0, "ruin_probability": 0}
    # Compound resampled equity-fraction returns (matches %-of-equity sizing).
    returns = _equity_fraction_returns(pnls, initial_cash)
    rng = np.random.default_rng(1337)
    final_returns = []
    worst_drawdowns = []
    ruin_count = 0
    for _ in range(scenarios):
        sampled = rng.choice(returns, size=returns.size, replace=True)
        equity = np.cumprod(1.0 + sampled)  # equity relative to start (starts at 1)
        running_max = np.maximum.accumulate(equity)
        drawdown = (equity - running_max) / running_max
        final_returns.append(float(equity[-1] - 1.0))
        worst_drawdowns.append(float(drawdown.min()))
        ruin_count += int(equity.min() <= 0.5)
    var_95 = float(np.percentile(final_returns, 5))
    tail = [value for value in final_returns if value <= var_95]
    return {
        "var_95": var_95,
        "expected_shortfall": float(np.mean(tail) if tail else var_95),
        "worst_drawdown": float(np.min(worst_drawdowns)),
        "ruin_probability": float(ruin_count / scenarios),
    }
