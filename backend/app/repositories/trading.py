from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import AccountSnapshot, Order, Position, StrategySettings, Trade
from app.models.enums import PositionStatus
from app.repositories.base import Repository


def day_start_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def week_start_utc() -> datetime:
    now = datetime.now(UTC)
    start = now - timedelta(days=now.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


class PositionRepository(Repository[Position]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Position)

    def open_positions(self) -> list[Position]:
        return list(self.db.query(Position).filter(Position.status == PositionStatus.open).all())

    def open_count(self) -> int:
        return self.db.query(Position).filter(Position.status == PositionStatus.open).count()

    def has_open(self, symbol: str) -> bool:
        """True when a position is already open on ``symbol`` (any direction).

        Guards against stacking several entries on the same pair across cycles —
        which would turn "diversified" positions into one concentrated bet."""
        return (
            self.db.query(Position.id)
            .filter(Position.status == PositionStatus.open, Position.symbol == symbol)
            .first()
            is not None
        )

    def open_notional(self) -> Decimal:
        """GROSS notional of all open positions (sum of |entry_price * quantity|).

        Longs and shorts both ADD to gross — this bounds total market exposure
        regardless of direction. Used by the gross exposure guard.
        """
        rows = (
            self.db.query(Position.side, Position.entry_price, Position.quantity)
            .filter(Position.status == PositionStatus.open)
            .all()
        )
        return Decimal(str(sum(abs(float(r.entry_price) * float(r.quantity)) for r in rows)))

    def net_notional(self) -> Decimal:
        """NET notional of all open positions (longs minus shorts, signed).

        A long and a short on the same asset partially offset, so net exposure
        measures the directional bias of the book. Positive = net long,
        negative = net short. Used by the net exposure guard — a market-neutral
        book (longs ≈ shorts) has near-zero net and should not be over-bound by
        the gross cap, while a one-way long book hits the net cap.
        """
        rows = (
            self.db.query(Position.side, Position.entry_price, Position.quantity)
            .filter(Position.status == PositionStatus.open)
            .all()
        )
        total = Decimal("0")
        for r in rows:
            signed = float(r.entry_price) * float(r.quantity)
            if r.side == "sell":  # short — subtract
                signed = -signed
            total += Decimal(str(signed))
        return total

    def open_symbols(self) -> list[str]:
        """Symbols of all open positions (deduped)."""
        rows = (
            self.db.query(Position.symbol)
            .filter(Position.status == PositionStatus.open)
            .distinct()
            .all()
        )
        return [r[0] for r in rows]


class OrderRepository(Repository[Order]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Order)


class TradeRepository(Repository[Trade]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Trade)

    def pnl_since(self, since: datetime) -> Decimal:
        value = self.db.query(func.coalesce(func.sum(Trade.realized_pnl), 0)).filter(
            Trade.traded_at >= since
        ).scalar()
        return Decimal(str(value))

    def daily_pnl(self) -> Decimal:
        return self.pnl_since(day_start_utc())

    def weekly_pnl(self) -> Decimal:
        return self.pnl_since(week_start_utc())


class AccountSnapshotRepository(Repository[AccountSnapshot]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, AccountSnapshot)

    def equity_at_period_start(self, since: datetime) -> Decimal | None:
        """Equity carried into the period: the latest snapshot strictly before
        `since`, falling back to the earliest snapshot within the period. Returns
        None when no snapshots exist (caller falls back to realized-only PnL)."""
        row = (
            self.db.query(AccountSnapshot)
            .filter(AccountSnapshot.created_at < since)
            .order_by(AccountSnapshot.created_at.desc())
            .first()
        )
        if row is None:
            row = (
                self.db.query(AccountSnapshot)
                .filter(AccountSnapshot.created_at >= since)
                .order_by(AccountSnapshot.created_at.asc())
                .first()
            )
        return Decimal(str(row.total_equity)) if row is not None else None


class StrategySettingsRepository(Repository[StrategySettings]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, StrategySettings)

    def current(self) -> StrategySettings:
        settings = self.db.query(StrategySettings).order_by(StrategySettings.id.asc()).first()
        if settings is None:
            settings = StrategySettings()
            self.db.add(settings)
            self.db.commit()
            self.db.refresh(settings)
        return settings

    def current_for_update(self) -> StrategySettings:
        """Like `current()` but takes a row lock held until the transaction
        commits, so concurrent risk approvals serialize (no-op on SQLite, which
        ignores SELECT ... FOR UPDATE)."""
        settings = (
            self.db.query(StrategySettings)
            .order_by(StrategySettings.id.asc())
            .with_for_update()
            .first()
        )
        if settings is None:
            return self.current()
        return settings
