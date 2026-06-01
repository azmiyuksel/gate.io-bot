from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import (
    BacktestStatus,
    CircuitBreakerScope,
    CircuitBreakerState,
    LogLevel,
    OrderSide,
    PaperBotStatus,
    PaperOrderStatus,
    PaperOrderType,
    OrderStatus,
    PositionStatus,
    RebalanceStatus,
    RebalanceTrigger,
    ReconcileAction,
    MarketRegimeType,
    StrategyHealthState,
    StrategyAlertLevel,
    UserRole,
    WalkForwardMode,
    WalkForwardStatus,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    exchange: Mapped[str] = mapped_column(String(32), default="gateio")
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    api_secret_encrypted: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    user: Mapped[User] = relationship(back_populates="api_keys")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[PositionStatus] = mapped_column(String(32), default=PositionStatus.open)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    take_profit: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    trailing_stop: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[OrderSide] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class StrategySettings(Base):
    __tablename__ = "strategy_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, default="capital_preservation_v1")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    max_capital_per_trade_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.01"))
    daily_max_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.02"))
    weekly_max_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    max_open_positions: Mapped[int] = mapped_column(default=3)
    min_reward_risk: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("2"))
    atr_multiplier: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("1.5"))
    trailing_stop_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.01"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.info)
    source: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


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


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), default="ema_rsi_atr_v1")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    status: Mapped[BacktestStatus] = mapped_column(String(32), default=BacktestStatus.pending)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    charts: Mapped[dict] = mapped_column(JSON, default=dict)
    optimization_results: Mapped[list] = mapped_column(JSON, default=list)
    walk_forward_results: Mapped[list] = mapped_column(JSON, default=list)
    monte_carlo_results: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trades: Mapped[list["BacktestTrade"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16))
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    pnl_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    run: Mapped[BacktestRun] = relationship(back_populates="trades")


class WalkForwardRun(Base):
    __tablename__ = "walkforward_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), default="ema_rsi_atr_v1")
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    mode: Mapped[WalkForwardMode] = mapped_column(String(32), default=WalkForwardMode.rolling)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    train_period_days: Mapped[int] = mapped_column(default=365)
    test_period_days: Mapped[int] = mapped_column(default=90)
    step_days: Mapped[int] = mapped_column(default=90)
    n_trials: Mapped[int] = mapped_column(default=30)
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    status: Mapped[WalkForwardStatus] = mapped_column(String(32), default=WalkForwardStatus.pending)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    aggregated_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    combined_equity_curve: Mapped[list] = mapped_column(JSON, default=list)
    monte_carlo_results: Mapped[dict] = mapped_column(JSON, default=dict)
    deployment_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    overfit_warnings: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    windows: Mapped[list["WalkForwardWindow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class WalkForwardWindow(Base):
    __tablename__ = "walkforward_windows"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("walkforward_runs.id", ondelete="CASCADE"))
    window_id: Mapped[int] = mapped_column(index=True)
    train_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    train_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    test_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    test_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    best_params: Mapped[dict] = mapped_column(JSON, default=dict)
    train_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    test_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    equity_curve: Mapped[list] = mapped_column(JSON, default=list)
    trades: Mapped[list] = mapped_column(JSON, default=list)
    wfe: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    overfit_warning: Mapped[bool] = mapped_column(Boolean, default=False)

    run: Mapped[WalkForwardRun] = relationship(back_populates="windows")


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    status: Mapped[PaperBotStatus] = mapped_column(String(32), default=PaperBotStatus.stopped)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    max_daily_loss_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.02"))
    max_drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.15"))
    max_exposure_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.30"))
    max_open_positions: Mapped[int] = mapped_column(default=3)
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
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    last_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
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


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, default="default")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    daily_max_risk_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.02"))
    weekly_max_risk_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.05"))
    monthly_max_risk_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.10"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    assets: Mapped[list["PortfolioAsset"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    allocations: Mapped[list["Allocation"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    rebalances: Mapped[list["RebalanceEvent"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    metrics: Mapped[list["PortfolioMetric"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")
    risk_snapshots: Mapped[list["RiskSnapshot"]] = relationship(back_populates="portfolio", cascade="all, delete-orphan")


class PortfolioAsset(Base):
    __tablename__ = "portfolio_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    position_size: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    risk_contribution: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    portfolio: Mapped[Portfolio] = relationship(back_populates="assets")


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    target_type: Mapped[str] = mapped_column(String(32))  # "strategy" or "asset"
    target_name: Mapped[str] = mapped_column(String(128))  # e.g., "EMA Strategy", "BTC_USDT"
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    performance_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    risk_adjusted_return: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    correlation_penalty: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    stability_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    drawdown_adjustment: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    portfolio: Mapped[Portfolio] = relationship(back_populates="allocations")


class RebalanceEvent(Base):
    __tablename__ = "rebalance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    trigger_reason: Mapped[RebalanceTrigger] = mapped_column(String(64))  # rebalance trigger
    previous_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    new_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_log: Mapped[str] = mapped_column(Text)
    status: Mapped[RebalanceStatus] = mapped_column(String(32))  # rebalance status
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    portfolio: Mapped[Portfolio] = relationship(back_populates="rebalances")


class PortfolioMetric(Base):
    __tablename__ = "portfolio_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    sharpe_ratio: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    correlation_risk_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    exposure_per_asset: Mapped[dict] = mapped_column(JSON, default=dict)
    exposure_per_strategy: Mapped[dict] = mapped_column(JSON, default=dict)
    volatility_adjusted_return: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))

    portfolio: Mapped[Portfolio] = relationship(back_populates="metrics")


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    scenario_name: Mapped[str] = mapped_column(String(64))  # scenario name
    simulated_loss: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    limit_status: Mapped[str] = mapped_column(String(32))  # limit status
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)

    portfolio: Mapped[Portfolio] = relationship(back_populates="risk_snapshots")


class MarketRegimeRecord(Base):
    __tablename__ = "market_regimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    regime_type: Mapped[MarketRegimeType] = mapped_column(String(32), default=MarketRegimeType.sideways)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.0"))
    rule_based_vote: Mapped[str] = mapped_column(String(32))
    clustering_vote: Mapped[str] = mapped_column(String(32))
    ml_vote: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class RegimeTransition(Base):
    __tablename__ = "regime_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    old_regime: Mapped[str] = mapped_column(String(32))
    new_regime: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.0"))
    trigger_event: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class RegimeFeatures(Base):
    __tablename__ = "regime_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    features_json: Mapped[dict] = mapped_column(JSON, default=dict)


class RegimeConfidence(Base):
    __tablename__ = "regime_confidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.0"))
    vote_weights: Mapped[dict] = mapped_column(JSON, default=dict)


class RegimePerformance(Base):
    __tablename__ = "regime_performance"

    id: Mapped[int] = mapped_column(primary_key=True)
    regime_type: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    total_trades: Mapped[int] = mapped_column(default=0)
    winning_trades: Mapped[int] = mapped_column(default=0)
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1.0"))
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class StrategyBaseline(Base):
    __tablename__ = "strategy_baselines"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expected_sharpe: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1.80"))
    expected_win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.58"))
    expected_profit_factor: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1.80"))
    expected_drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0.12"))
    expected_trade_frequency: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("5.0"))  # per week
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class StrategyHealthLog(Base):
    __tablename__ = "strategy_health_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    rolling_sharpe: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    rolling_win_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    rolling_profit_factor: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    rolling_drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    expectancy: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    health_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("100.0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class StrategyDriftScore(Base):
    __tablename__ = "strategy_drift_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    drift_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    deviation_details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class StrategyAlert(Base):
    __tablename__ = "strategy_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    alert_level: Mapped[StrategyAlertLevel] = mapped_column(String(16), default=StrategyAlertLevel.green)
    message: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(String(64))  # none, risk_reduced_50, block_new_trades, pause_strategy
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class StrategyStateHistory(Base):
    __tablename__ = "strategy_state_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    old_state: Mapped[StrategyHealthState] = mapped_column(String(32))
    new_state: Mapped[StrategyHealthState] = mapped_column(String(32))
    trigger_reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class AccountSnapshot(Base):
    """Point-in-time snapshot of the real exchange account balance and equity."""

    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), default="gateio", index=True)
    quote_currency: Mapped[str] = mapped_column(String(16), default="USDT")
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    available_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    locked_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    positions_value: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    total_equity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    balances: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(32), default="exchange")  # exchange | fallback
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ReconciliationLog(Base):
    """Audit record of an order reconciliation pass against the exchange."""

    __tablename__ = "reconciliation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[ReconcileAction] = mapped_column(String(32), default=ReconcileAction.no_change)
    previous_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class CircuitBreakerEvent(Base):
    """Global kill-switch state transitions. The latest row is the current state."""

    __tablename__ = "circuit_breaker_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[CircuitBreakerState] = mapped_column(String(16), default=CircuitBreakerState.armed)
    scope: Mapped[CircuitBreakerScope] = mapped_column(String(32), default=CircuitBreakerScope.manual)
    reason: Mapped[str] = mapped_column(Text)
    triggered_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(64), default="system")  # system | user email
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)



