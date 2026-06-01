from decimal import Decimal

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import PaperEquityCurve, PaperTrade


class PaperMetrics:
    def __init__(self, db: Session, account_id: int) -> None:
        self.db = db
        self.account_id = account_id

    def summary(self) -> dict:
        trades = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.account_id == self.account_id)
            .order_by(PaperTrade.traded_at.desc())
            .limit(100)
            .all()
        )
        equity_points = (
            self.db.query(PaperEquityCurve)
            .filter(PaperEquityCurve.account_id == self.account_id)
            .order_by(PaperEquityCurve.timestamp.asc())
            .all()
        )
        pnls = np.array([float(trade.realized_pnl) for trade in trades], dtype="float64")
        wins = pnls[pnls > 0]
        equity = np.array([float(point.equity) for point in equity_points], dtype="float64")
        returns = np.diff(equity) / np.maximum(equity[:-1], 1) if len(equity) > 1 else np.array([])
        sharpe = float((returns.mean() / returns.std()) * np.sqrt(365 * 24)) if returns.size and returns.std() else 0
        drawdown = min([float(point.drawdown) for point in equity_points] + [0])
        return {
            "realized_pnl": float(sum((trade.realized_pnl for trade in trades), Decimal("0"))),
            "win_rate_rolling_100": float(len(wins) / len(pnls)) if len(pnls) else 0,
            "rolling_sharpe": sharpe,
            "drawdown": drawdown,
        }
