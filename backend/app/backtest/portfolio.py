from dataclasses import dataclass, field

import pandas as pd

from app.backtest.models import BacktestPosition, BacktestTradeResult


@dataclass
class Portfolio:
    initial_cash: float
    cash: float = field(init=False)
    realized_pnl: float = 0
    positions: list[BacktestPosition] = field(default_factory=list)
    closed_trades: list[BacktestTradeResult] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def can_open(self, max_open_positions: int) -> bool:
        return len(self.positions) < max_open_positions

    def open_position(self, position: BacktestPosition, gross_cost: float) -> None:
        self.cash -= gross_cost + position.fee_paid
        self.positions.append(position)

    def close_position(
        self, position: BacktestPosition, exit_time: pd.Timestamp, exit_price: float, fee: float, reason: str
    ) -> BacktestTradeResult:
        gross_value = exit_price * position.quantity
        pnl = gross_value - (position.entry_price * position.quantity) - position.fee_paid - fee
        self.cash += gross_value - fee
        self.realized_pnl += pnl
        self.positions.remove(position)
        trade = BacktestTradeResult(
            symbol=position.symbol,
            side="long",
            entry_time=position.entry_time,
            exit_time=exit_time,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            fee=position.fee_paid + fee,
            pnl=pnl,
            pnl_pct=pnl / max(position.entry_price * position.quantity, 1e-12),
            exit_reason=reason,
        )
        self.closed_trades.append(trade)
        return trade

    def mark_to_market(self, timestamp: pd.Timestamp, price: float) -> dict:
        unrealized = sum((price - position.entry_price) * position.quantity for position in self.positions)
        equity = self.cash + sum(position.quantity * price for position in self.positions)
        point = {
            "timestamp": timestamp.isoformat(),
            "cash": self.cash,
            "equity": equity,
            "unrealized_pnl": unrealized,
            "realized_pnl": self.realized_pnl,
            "open_positions": len(self.positions),
        }
        self.equity_curve.append(point)
        return point
