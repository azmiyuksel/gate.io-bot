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
from app.models.enums import (
    BacktestStatus,
    CircuitBreakerScope,
    CircuitBreakerState,
    ReconcileAction,
    WalkForwardMode,
    WalkForwardStatus,
)

# Re-export models from domain-specific files so existing imports keep working
from app.models.auth import ApiKey, AuditLog, RefreshToken, User  # noqa: F401
from app.models.trading import (  # noqa: F401
    HistoricalCandle,
    Order,
    Position,
    StrategySettings,
    SystemLog,
    Trade,
    WorkerHeartbeat,
)
from app.models.paper import (  # noqa: F401
    PaperAccount,
    PaperEquityCurve,
    PaperLog,
    PaperOrder,
    PaperPosition,
    PaperTrade,
)
from app.models.portfolio import (  # noqa: F401
    Allocation,
    Portfolio,
    PortfolioAsset,
    PortfolioMetric,
    RebalanceEvent,
    RiskSnapshot,
)
from app.models.market import (  # noqa: F401
    MarketRegimeRecord,
    RegimeConfidence,
    RegimeFeatures,
    RegimePerformance,
    RegimeTransition,
)
from app.models.strategy import (  # noqa: F401
    StrategyAlert,
    StrategyBaseline,
    StrategyDriftScore,
    StrategyHealthLog,
    StrategyStateHistory,
)
from app.models.execution import (  # noqa: F401
    ExecutionFill,
    ExecutionMetric,
    ExecutionOrder,
    ExecutionReport,
    LatencyLog,
    SlippageLog,
)
from app.models.data_quality import (  # noqa: F401
    DataQualityReport,
    MarketDataAnomaly,
    MarketDataClean,
    MarketDataHealthLog,
    MarketDataRaw,
)
from app.models.research import (  # noqa: F401
    ABTestResult,
    FeatureRecord,
    HypothesisTest,
    ResearchExperiment,
    ResearchStrategy,
    StrategyVersion,
)
from app.models.learning import (  # noqa: F401
    DiscoveredFeature,
    KnowledgeEntry,
    LearningCycle,
    LearningReport,
    PromotionRequest,
    StrategyRanking,
)


def now_utc() -> datetime:
    return datetime.now(UTC)


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
