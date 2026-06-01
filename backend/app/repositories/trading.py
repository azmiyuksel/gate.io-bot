from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Order, Position, StrategySettings, Trade
from app.models.enums import PositionStatus
from app.repositories.base import Repository


class PositionRepository(Repository[Position]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, Position)

    def open_positions(self) -> list[Position]:
        return list(self.db.query(Position).filter(Position.status == PositionStatus.open).all())

    def open_count(self) -> int:
        return self.db.query(Position).filter(Position.status == PositionStatus.open).count()


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
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.pnl_since(start)

    def weekly_pnl(self) -> Decimal:
        start = datetime.now(UTC) - timedelta(days=datetime.now(UTC).weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.pnl_since(start)


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
