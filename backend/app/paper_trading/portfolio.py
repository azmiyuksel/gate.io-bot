from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from sqlalchemy import func

from app.models.entities import PaperAccount, PaperEquityCurve, PaperPosition

# Minimum interval between equity curve recordings to prevent DB exhaustion.
# Set to 5 minutes (300 seconds) — equity is sampled on each tick cycle.
_EQUITY_RECORD_INTERVAL_SECONDS = 300


class PaperPortfolio:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self._last_equity_record_ts: datetime | None = None

    def equity(self) -> Decimal:
        """Mark-to-market account equity.

        The broker mutates ``cash_balance`` by the full notional on entry: a long
        buy deducts ``qty*price`` (the position is now an asset), a short sell adds
        ``qty*price`` (the position is now a liability). Equity must therefore add
        the current MARKET VALUE of each open position back, not merely its
        unrealized PnL — otherwise every fresh long understates equity by its cost
        basis (≈ the whole notional), which instantly trips the daily-loss/drawdown
        guard and pauses the bot after a single trade. Algebraically this equals
        ``cash + fees + Σ unrealized``; expressed via market value it is:

            equity = cash + Σ_long(qty*last) − Σ_short(qty*last)
        """
        total = self.account.cash_balance
        for position in self.open_positions():
            market_value = position.quantity * position.last_price
            if position.side == "sell":
                total -= market_value
            else:
                total += market_value
        return total

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
        changed = False
        for position in self.open_positions():
            if position.symbol != symbol:
                continue
            position.last_price = price
            if position.side == "sell":
                position.unrealized_pnl = (position.average_entry_price - price) * position.quantity
            else:
                position.unrealized_pnl = (price - position.average_entry_price) * position.quantity
            changed = True
        if changed:
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
