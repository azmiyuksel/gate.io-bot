from decimal import Decimal

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import PaperEquityCurve, PaperTrade

# Bound the equity series pulled for the rolling Sharpe so the cost stays flat as
# history grows. At the 5-min recording cadence this window spans ~3.5 days, which
# is an appropriate horizon for a "rolling" figure. Drawdown uses a SQL aggregate
# over the full history (cheap), so it is unaffected by this window.
_SHARPE_WINDOW = 1000


class PaperMetrics:
    def __init__(self, db: Session, account_id: int) -> None:
        self.db = db
        self.account_id = account_id

    def summary(self) -> dict:
        trades = (
            self.db.query(PaperTrade.realized_pnl)
            .filter(PaperTrade.account_id == self.account_id)
            .order_by(PaperTrade.traded_at.desc())
            .limit(100)
            .all()
        )
        # Pull only the most recent equity points (timestamp asc) for the rolling
        # Sharpe instead of the whole curve. Fetch newest-first then reverse so the
        # series stays chronological while the DB only scans the index tail.
        recent_desc = (
            self.db.query(PaperEquityCurve.timestamp, PaperEquityCurve.equity)
            .filter(PaperEquityCurve.account_id == self.account_id)
            .order_by(PaperEquityCurve.timestamp.desc())
            .limit(_SHARPE_WINDOW)
            .all()
        )
        equity_points = list(reversed(recent_desc))

        pnls = np.array([float(pnl) for (pnl,) in trades], dtype="float64")
        wins = pnls[pnls > 0]
        equity = np.array([float(eq) for (_, eq) in equity_points], dtype="float64")
        returns = np.log(equity[1:] / np.maximum(equity[:-1], 1)) if len(equity) > 1 else np.array([])
        # Annualization: compute actual observations per year from timestamps
        if len(equity_points) >= 2:
            first_ts = equity_points[0][0]
            last_ts = equity_points[-1][0]
            span_seconds = (last_ts - first_ts).total_seconds() if last_ts > first_ts else 300
            obs_per_second = len(equity_points) / max(span_seconds, 1)
            annual_factor = np.sqrt(obs_per_second * 86400 * 365)
        else:
            annual_factor = np.sqrt(365 * 24 * 12)  # 5-min default
        sharpe = float(returns.mean() / returns.std() * annual_factor) if returns.size and returns.std() else 0
        # Max drawdown over the FULL history via a SQL aggregate (indexed, constant
        # cost) rather than loading every point into Python.
        min_dd = (
            self.db.query(func.min(PaperEquityCurve.drawdown))
            .filter(PaperEquityCurve.account_id == self.account_id)
            .scalar()
        )
        drawdown = min(float(min_dd) if min_dd is not None else 0.0, 0.0)
        return {
            "realized_pnl": float(sum((Decimal(str(p)) for (p,) in trades), Decimal("0"))),
            "win_rate_rolling_100": float(len(wins) / len(pnls)) if len(pnls) else 0,
            "rolling_sharpe": sharpe,
            "drawdown": drawdown,
        }
