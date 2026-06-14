from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperEquityCurve, PaperLog
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.models import MarketData, TradingSignal
from app.paper_trading.portfolio import PaperPortfolio

_ROLLING_24H = timedelta(hours=24)


class PaperRiskSimulator:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self.portfolio = PaperPortfolio(db, account)
        self._equity_snapshots: deque[tuple[datetime, Decimal]] = deque()

    def approve_signal(self, signal: TradingSignal, data: MarketData) -> tuple[bool, str]:
        if self.account.status != PaperBotStatus.running:
            return False, "system_not_running"
        equity = self.portfolio.equity()
        if equity <= 0:
            return False, "no_equity"
        open_positions = self.portfolio.open_positions()
        if len(open_positions) >= self.account.max_open_positions:
            return False, "max_open_positions"
        if any(p.symbol == signal.symbol for p in open_positions):
            return False, "already_in_position"
        if self.portfolio.exposure_pct() >= self.account.max_exposure_pct:
            return False, "max_exposure"
        latest_dd = self._check_drawdown()
        if abs(latest_dd) >= self.account.max_drawdown_pct:
            self.pause("max_drawdown_reached")
            return False, "max_drawdown_reached"
        if self._daily_loss_pct() >= self.account.max_daily_loss_pct:
            self.pause("daily_loss_limit_reached")
            return False, "daily_loss_limit_reached"
        return True, "approved"

    def pause(self, reason: str) -> None:
        self.account.status = PaperBotStatus.paused
        self._paused_reason = reason
        self._paused_at = datetime.now(UTC)
        self.db.add(PaperLog(account_id=self.account.id, level=LogLevel.warning, event="system_paused", message=reason))
        self.db.commit()

    def maybe_auto_resume(self) -> bool:
        if self.account.status != PaperBotStatus.paused:
            return False
        if not hasattr(self, "_paused_at"):
            return False
        cooldown_hours = 4 if getattr(self, "_paused_reason", "") == "max_drawdown_reached" else 1
        if datetime.now(UTC) - self._paused_at < timedelta(hours=cooldown_hours):
            return False
        equity = self.portfolio.equity()
        if equity <= 0:
            return False
        dd = self._check_drawdown()
        if dd >= self.account.max_drawdown_pct:
            return False
        loss = self._daily_loss_pct()
        if loss >= self.account.max_daily_loss_pct:
            return False
        self.account.status = PaperBotStatus.running
        self._log_info("system_auto_resumed", "Auto-resumed after cooldown")
        return True

    def _log_info(self, event: str, message: str) -> None:
        self.db.add(PaperLog(account_id=self.account.id, level=LogLevel.info, event=event, message=message))
        self.db.commit()

    def _check_drawdown(self) -> Decimal:
        point = (
            self.db.query(PaperEquityCurve)
            .filter(PaperEquityCurve.account_id == self.account.id)
            .order_by(PaperEquityCurve.timestamp.desc())
            .first()
        )
        if point is None:
            return Decimal("0")
        return abs(point.drawdown)

    def _daily_loss_pct(self) -> Decimal:
        equity = self.portfolio.equity()
        now = datetime.now(UTC)
        cutoff = now - _ROLLING_24H
        self._equity_snapshots.append((now, equity))
        while self._equity_snapshots and self._equity_snapshots[0][0] < cutoff:
            self._equity_snapshots.popleft()
        if not self._equity_snapshots:
            return Decimal("0")
        peak_24h = max(snap[1] for snap in self._equity_snapshots)
        if peak_24h <= 0:
            return Decimal("0")
        loss = max(peak_24h - equity, Decimal("0"))
        return loss / peak_24h
