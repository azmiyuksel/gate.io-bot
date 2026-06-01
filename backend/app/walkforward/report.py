import plotly.graph_objects as go


def build_walkforward_report(aggregated: dict, windows: list, combined_equity_curve: list[dict]) -> dict:
    x = [point["timestamp"] for point in combined_equity_curve]
    y = [point["equity"] for point in combined_equity_curve]
    equity_fig = go.Figure(data=[go.Scatter(x=x, y=y, mode="lines", name="Combined OOS Equity")])
    window_fig = go.Figure(
        data=[
            go.Bar(
                x=[window.window_id for window in windows],
                y=[window.test_metrics.get("net_profit", 0) for window in windows],
                name="Window Net Profit",
            )
        ]
    )
    rolling_sharpe = go.Figure(
        data=[
            go.Scatter(
                x=[window.window_id for window in windows],
                y=[window.test_metrics.get("sharpe_ratio", 0) for window in windows],
                mode="lines+markers",
                name="Rolling Sharpe",
            )
        ]
    )
    rolling_dd = go.Figure(
        data=[
            go.Scatter(
                x=[window.window_id for window in windows],
                y=[window.test_metrics.get("max_drawdown", 0) for window in windows],
                mode="lines+markers",
                name="Rolling Drawdown",
            )
        ]
    )
    wfe_history = go.Figure(
        data=[
            go.Scatter(
                x=[window.window_id for window in windows],
                y=[window.wfe for window in windows],
                mode="lines+markers",
                name="WFE",
            )
        ]
    )
    return {
        "summary": aggregated,
        "charts": {
            "combined_equity_curve": equity_fig.to_json(),
            "window_performance": window_fig.to_json(),
            "rolling_sharpe": rolling_sharpe.to_json(),
            "rolling_drawdown": rolling_dd.to_json(),
            "wfe_history": wfe_history.to_json(),
        },
    }


def pdf_report_placeholder(run_id: int, aggregated: dict) -> bytes:
    return (
        f"Walk-forward report #{run_id}\n"
        f"Robustness: {aggregated.get('robustness_score', 0)}\n"
        f"WFE: {aggregated.get('wfe', 0)}\n"
        f"Consistency: {aggregated.get('consistency_score', 0)}\n"
    ).encode()
