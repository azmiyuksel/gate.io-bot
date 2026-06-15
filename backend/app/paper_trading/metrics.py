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
        returns = np.log(equity[1:] / np.maximum(equity[:-1], 1)) if len(equity) > 1 else np.array([])
        # Annualization: compute actual observations per year from timestamps
        if len(equity_points) >= 2:
            first_ts = equity_points[0].timestamp
            last_ts = equity_points[-1].timestamp
            span_seconds = (last_ts - first_ts).total_seconds() if last_ts > first_ts else 300
            obs_per_second = len(equity_points) / max(span_seconds, 1)
            annual_factor = np.sqrt(obs_per_second * 86400 * 365)
        else:
            annual_factor = np.sqrt(365 * 24 * 12)  # 5-min default
        sharpe = float(returns.mean() / returns.std() * annual_factor) if returns.size and returns.std() else 0
        drawdown = min([float(point.drawdown) for point in equity_points] + [0])
        return {
            "realized_pnl": float(sum((trade.realized_pnl for trade in trades), Decimal("0"))),
            "win_rate_rolling_100": float(len(wins) / len(pnls)) if len(pnls) else 0,
            "rolling_sharpe": sharpe,
            "drawdown": drawdown,
        }
