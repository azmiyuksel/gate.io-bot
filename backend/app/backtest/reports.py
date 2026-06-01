import plotly.graph_objects as go

from app.backtest.models import BacktestTradeResult


def build_plotly_report(equity_curve: list[dict], trades: list[BacktestTradeResult]) -> dict:
    equity_x = [point["timestamp"] for point in equity_curve]
    equity_y = [point["equity"] for point in equity_curve]
    peak = []
    max_value = 0.0
    drawdown = []
    for value in equity_y:
        max_value = max(max_value, value)
        peak.append(max_value)
        drawdown.append((value - max_value) / max_value if max_value else 0)

    equity_fig = go.Figure(data=[go.Scatter(x=equity_x, y=equity_y, mode="lines", name="Equity")])
    drawdown_fig = go.Figure(data=[go.Scatter(x=equity_x, y=drawdown, mode="lines", name="Drawdown")])
    pnl_values = [trade.pnl for trade in trades]
    histogram_fig = go.Figure(data=[go.Histogram(x=pnl_values, name="Trade PnL")])
    distribution_fig = go.Figure(
        data=[go.Box(y=pnl_values, name="Profit/Loss Distribution", boxmean=True)]
    )
    monthly_fig = go.Figure(data=[go.Bar(x=[], y=[], name="Monthly Returns")])
    return {
        "equity_curve": equity_fig.to_json(),
        "drawdown_curve": drawdown_fig.to_json(),
        "monthly_returns": monthly_fig.to_json(),
        "trade_distribution": distribution_fig.to_json(),
        "profit_loss_histogram": histogram_fig.to_json(),
    }


def pdf_report_placeholder(run_id: int) -> bytes:
    return f"Backtest report #{run_id}\nPDF rendering adapter can be connected here.\n".encode()
