from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import (
    LogLevel,
    OrderSide,
    PaperBotStatus,
    PaperMarginMode,
    PaperOrderStatus,
    PaperOrderType,
    PaperPositionMode,
    PaperPositionSide,
    PaperTimeInForce,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="default", unique=True)
    status: Mapped[PaperBotStatus] = mapped_column(String(32), default=PaperBotStatus.stopped)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    # Auto-pause thresholds (widened for leverage; see paper_max_*_pct in config).
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.08"))
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.30"))
    # Futures: total open notional may reach leverage * equity, so the exposure cap
    # is expressed in leverage terms (5x) rather than a spot <=1 fraction.
    max_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("5.00"))
    max_open_positions: Mapped[int] = mapped_column(default=8)
    # Position-accounting mode: one_way (the legacy netting auto-flip behaviour)
    # or hedge (long & short open simultaneously on the same symbol).
    position_mode: Mapped[PaperPositionMode] = mapped_column(String(8), default=PaperPositionMode.one_way)
    # Margin mode is documentary parity with live (cross vs isolated); the paper
    # liquidation engine uses a single maintenance tier regardless of mode.
    margin_mode: Mapped[PaperMarginMode] = mapped_column(String(8), default=PaperMarginMode.cross)
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
    # Order semantics: time-in-force (GTC/IOC/FOK/POST), post-only (maker-only),
    # reduce-only (cannot increase position), OCO pair link (when one fills the
    # other is auto-cancelled), and position_side for hedge-mode accounting.
    time_in_force: Mapped[PaperTimeInForce] = mapped_column(String(8), default=PaperTimeInForce.gtc)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    post_only: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_order_id: Mapped[int | None] = mapped_column(nullable=True)
    position_side: Mapped[PaperPositionSide | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped[PaperAccount] = relationship(back_populates="orders")


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    # The dashboard/metrics path filters by account and reads newest-first; the
    # composite index avoids a full scan as the trade history grows.
    __table_args__ = (
        Index("ix_paper_trades_account_traded", "account_id", "traded_at"),
    )

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
    # The trade engine and risk checks query open positions per account on every
    # tick/cycle; index the exact (account_id, is_open) filter they use.
    __table_args__ = (
        Index("ix_paper_positions_account_open", "account_id", "is_open"),
    )

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
    # Initial stop-loss at position open: the R baseline for scale-out and
    # risk/reward accounting. Unlike `stop_loss` (which gets moved by breakeven
    # and trailing), this stays fixed at the original ATR-based stop so partial
    # profit-taking can key off the TRUE risk R = |entry - initial_stop|.
    initial_stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    # Whether the partial profit-taking (scale-out) leg has already fired, so it
    # fires at most once per position.
    scaled_out: Mapped[bool] = mapped_column(Boolean, default=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Futures realism fields: leverage + posted margin + liquidation/mark price so
    # a leveraged loser can be force-closed at maintenance instead of letting
    # equity sink unboundedly negative. NULL leverage means cash/spot (1x).
    leverage: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    margin: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    liquidation_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    # Signed funding accrual: ``last_funding_ts`` tracks the previous 8h
    # settlement so the engine can charge/pay funding periodically (not just at
    # close as a flat positive daily tax). ``last_funding_rate`` is cached for
    # dashboard display of the in-force carry.
    last_funding_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_funding_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 10), nullable=True)
    # Hedge-mode side (long/short/net). In one-way mode this is derived from
    # ``side`` ("buy" -> long, "sell" -> short) but is stored explicitly so the
    # one-way -> hedge migration need not backfill positions.
    position_side: Mapped[PaperPositionSide | None] = mapped_column(String(8), nullable=True)

    account: Mapped[PaperAccount] = relationship(back_populates="positions")


class PaperEquityCurve(Base):
    __tablename__ = "paper_equity_curve"
    # Equity points are recorded every 5 min (grows fast) and queried per account
    # ordered/ranged by timestamp (metrics, risk, equity chart). A composite index
    # serves those far better than the standalone timestamp index alone.
    __table_args__ = (
        Index("ix_paper_equity_account_ts", "account_id", "timestamp"),
    )

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
    # signal-diagnostics filters (account_id, event, created_at) and the worker's
    # auto-resume scans logs by event; index that exact access pattern.
    __table_args__ = (
        Index("ix_paper_logs_account_event_created", "account_id", "event", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.info)
    event: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
