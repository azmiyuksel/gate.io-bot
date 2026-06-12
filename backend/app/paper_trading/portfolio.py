from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from sqlalchemy import func

from app.models.entities import PaperAccount, PaperEquityCurve, PaperPosition

# Minimum interval between equity curve recordings to prevent DB exhaustion.
# Set to 1 hour (3600 seconds) — equity is sampled once per candle close.
_EQUITY_RECORD_INTERVAL_SECONDS = 3600


class PaperPortfolio:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self._last_equity_record_ts: datetime | None = None

    def equity(self) -> Decimal:
        open_positions = self.open_positions()
        exposure_value = sum(position.quantity * position.last_price for position in open_positions)
        return self.account.cash_balance + exposure_value

    def open_positions(self) -> list[PaperPosition]:
        return (
            self.db.query(PaperPosition)
            .filter(PaperPosition.account_id == self.account.id, PaperPosition.is_open.is_(True))
            .all()
        )

    def exposure_pct(self) -> Decimal:
        equity = self.equity()
        if equity <= 0:
            return Decimal("0")
        exposure = sum(position.quantity * position.last_price for position in self.open_positions())
        return exposure / equity

    def mark_price(self, symbol: str, price: Decimal) -> None:
        for position in self.open_positions():
            if position.symbol != symbol:
                continue
            position.last_price = price
            position.unrealized_pnl = (price - position.average_entry_price) * position.quantity
        self.db.commit()

    def record_equity(self) -> PaperEquityCurve | None:
        """Record equity curve point, throttled to once per interval.

        Returns the new ``PaperEquityCurve`` row if recorded, or ``None`` if
        skipped due to throttling. This prevents DB exhaustion from
        high-frequency tick data.
        """
        now = datetime.now(UTC)
        if self._last_equity_record_ts is not None:
            elapsed = (now - self._last_equity_record_ts).total_seconds()
            if elapsed < _EQUITY_RECORD_INTERVAL_SECONDS:
                return None

        equity = self.equity()
        peak_result = self.db.query(func.max(PaperEquityCurve.equity)).filter(
            PaperEquityCurve.account_id == self.account.id
        ).scalar()
        peak = max(Decimal(str(peak_result)) if peak_result is not None else Decimal("0"), equity)
        drawdown = (equity - peak) / peak if peak else Decimal("0")
        unrealized = sum(position.unrealized_pnl for position in self.open_positions())
        point = PaperEquityCurve(
            account_id=self.account.id,
            timestamp=now,
            cash_balance=self.account.cash_balance,
            equity=equity,
            realized_pnl=self.account.realized_pnl,
            unrealized_pnl=unrealized,
            drawdown=drawdown,
            exposure=self.exposure_pct(),
        )
        self.db.add(point)
        self.db.commit()
        self.db.refresh(point)
        self._last_equity_record_ts = now
        return point
