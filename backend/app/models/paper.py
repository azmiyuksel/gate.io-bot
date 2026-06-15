from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import LogLevel, OrderSide, PaperBotStatus, PaperOrderStatus, PaperOrderType


def now_utc() -> datetime:
    return datetime.now(UTC)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    status: Mapped[PaperBotStatus] = mapped_column(String(32), default=PaperBotStatus.stopped)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.25"))
    max_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.50"))
    max_open_positions: Mapped[int] = mapped_column(default=8)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    orders: Mapped[list["PaperOrder"]] = relationship(back_populates="account", cascade="all, delete-orphan")
    positions: Mapped[list["PaperPosition"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(String(16))
    order_type: Mapped[PaperOrderType] = mapped_column(String(32), default=PaperOrderType.market)
    status: Mapped[PaperOrderStatus] = mapped_column(String(32), default=PaperOrderStatus.pending)
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    fee_paid: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    latency_ms: Mapped[int] = mapped_column(default=0)
    signal: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[PaperAccount] = relationship(back_populates="orders")


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_orders.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8), default="buy")
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    last_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    trailing_stop: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    highest_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    breakeven_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[PaperAccount] = relationship(back_populates="positions")


class PaperEquityCurve(Base):
    __tablename__ = "paper_equity_curve"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    exposure: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))


class PaperLog(Base):
    __tablename__ = "paper_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.info)
    event: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
