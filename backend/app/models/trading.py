from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import LogLevel, OrderSide, OrderStatus, PositionStatus


def now_utc() -> datetime:
    return datetime.now(UTC)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[PositionStatus] = mapped_column(
        String(32), default=PositionStatus.open, index=True
    )
    side: Mapped[OrderSide] = mapped_column(String(16), default=OrderSide.buy)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    take_profit: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    trailing_stop: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    breakeven_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(String(16))
    status: Mapped[OrderStatus] = mapped_column(String(32), default=OrderStatus.open)
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    strategy_name: Mapped[str] = mapped_column(String(128), default="capital_preservation_v1", index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class StrategySettings(Base):
    __tablename__ = "strategy_settings"
    __table_args__ = (
        CheckConstraint(
            "max_capital_per_trade_pct > 0 AND max_capital_per_trade_pct <= 0.20",
            name="ck_max_capital_per_trade_pct",
        ),
        CheckConstraint(
            "daily_max_loss_pct > 0 AND daily_max_loss_pct <= 0.10",
            name="ck_daily_max_loss_pct",
        ),
        CheckConstraint(
            "weekly_max_loss_pct > 0 AND weekly_max_loss_pct <= 0.30",
            name="ck_weekly_max_loss_pct",
        ),
        CheckConstraint(
            "trailing_stop_pct > 0 AND trailing_stop_pct < 1",
            name="ck_trailing_stop_pct",
        ),
        CheckConstraint(
            "atr_multiplier > 0 AND atr_multiplier <= 10",
            name="ck_atr_multiplier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, default="capital_preservation_v1")
    # Safe default: a new strategy is DISABLED until explicitly enabled (matches the
    # capital-preservation activation gate; live entries also require BOT_ENABLED).
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_capital_per_trade_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    daily_max_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    weekly_max_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.15"))
    max_open_positions: Mapped[int] = mapped_column(default=8)
    min_reward_risk: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("1.5"))
    atr_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("2.0"))
    trailing_stop_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.015"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.info, index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class HistoricalCandle(Base):
    __tablename__ = "historical_candles"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candle_symbol_tf_ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    high: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    low: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(32), default="gateio")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class WorkerHeartbeat(Base):
    """Liveness signal written by a background worker each cycle.

    A separate process (the API server's watchdog) reads ``last_beat_at`` to
    detect a dead or stuck worker — critical for live trading, where a silently
    crashed scheduler leaves open positions unmanaged. One upserted row per
    worker name.
    """
    __tablename__ = "worker_heartbeats"

    id: Mapped[int] = mapped_column(primary_key=True)
    worker: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    last_beat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
