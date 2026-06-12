from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import PaperAccount, PaperLog
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.models import MarketData, TradingSignal
from app.paper_trading.portfolio import PaperPortfolio


class PaperRiskSimulator:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self.portfolio = PaperPortfolio(db, account)
        self._daily_start_equity: Decimal | None = None
        self._daily_start_date: datetime | None = None

    def approve_signal(self, signal: TradingSignal, data: MarketData) -> tuple[bool, str]:
        if self.account.status != PaperBotStatus.running:
            return False, "system_not_running"
        equity = self.portfolio.equity()
        if equity <= 0:
            return False, "no_equity"
        if len(self.portfolio.open_positions()) >= self.account.max_open_positions:
            return False, "max_open_positions"
        if self.portfolio.exposure_pct() >= self.account.max_exposure_pct:
            return False, "max_exposure"
        latest_dd = self._latest_drawdown()
        if abs(latest_dd) >= self.account.max_drawdown_pct:
            self.pause("max_drawdown_reached")
            return False, "max_drawdown_reached"
        if self._daily_loss_pct() >= self.account.max_daily_loss_pct:
            self.pause("daily_loss_limit_reached")
            return False, "daily_loss_limit_reached"
        if data.high and data.low and data.price and (data.high - data.low) / data.price > get_settings().strategy_max_24h_range_pct:
            return False, "volatility_filter"
        return True, "approved"

    def pause(self, reason: str) -> None:
        self.account.status = PaperBotStatus.paused
        self.db.add(PaperLog(account_id=self.account.id, level=LogLevel.warning, event="system_paused", message=reason))
        self.db.commit()

    def _latest_drawdown(self) -> Decimal:
        point = self.portfolio.record_equity()
        return abs(point.drawdown)

    def _daily_loss_pct(self) -> Decimal:
        equity = self.portfolio.equity()
        today = datetime.now(UTC).date()
        if self._daily_start_date != today or self._daily_start_equity is None:
            self._daily_start_equity = equity
            self._daily_start_date = today
        if self._daily_start_equity <= 0:
            return Decimal("0")
        loss = max(self._daily_start_equity - equity, Decimal("0"))
        return loss / self._daily_start_equity
