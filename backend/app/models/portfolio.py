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
from app.models.enums import RebalanceStatus, RebalanceTrigger


def now_utc() -> datetime:
    return datetime.now(UTC)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, default="default")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
    peak_equity: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("10000"))
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
