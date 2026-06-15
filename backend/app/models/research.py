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


def now_utc() -> datetime:
    return datetime.now(UTC)


class ResearchStrategy(Base):
    """A discovered strategy lineage (one row per distinct strategy)."""

    __tablename__ = "research_strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    template: Mapped[str] = mapped_column(String(64), default="ema_rsi_atr")
    signature: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="CANDIDATE", index=True)
    origin: Mapped[str] = mapped_column(String(32), default="generated")
    family_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    best_fitness: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    best_version_id: Mapped[int | None] = mapped_column(nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    versions: Mapped[list["StrategyVersion"]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class StrategyVersion(Base):
    """A single evaluated version (parameters + metrics) of a strategy."""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("research_strategies.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(default=1)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    walk_forward: Mapped[list] = mapped_column(JSON, default=list)
    monte_carlo: Mapped[dict] = mapped_column(JSON, default=dict)
    sharpe: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    profit_factor: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    stability_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    consistency_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    fitness: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), index=True)
    overfit: Mapped[bool] = mapped_column(Boolean, default=False)
    total_trades: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)

    strategy: Mapped[ResearchStrategy] = relationship(back_populates="versions")


class ResearchExperiment(Base):
    """An experiment run (generation/mutation/evaluation/ab-test)."""

    __tablename__ = "research_experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_strategies.id", ondelete="SET NULL"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT")
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    fitness: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HypothesisTest(Base):
    """A testable market hypothesis and its statistical evaluation."""

    __tablename__ = "hypothesis_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    statement: Mapped[str] = mapped_column(Text)
    feature: Mapped[str] = mapped_column(String(64), index=True)
    condition: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="UNTESTED", index=True)
    supported: Mapped[bool] = mapped_column(Boolean, default=False)
    edge: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    p_value: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1"))
    sample_size: Mapped[int] = mapped_column(default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT")
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class FeatureRecord(Base):
    """Central feature store entry with profitability/stability metadata."""

    __tablename__ = "feature_store"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(16), default="PRICE", index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT", index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    importance_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    correlation_with_profit: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    stability_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    feature_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ABTestResult(Base):
    """Head-to-head comparison of two strategy versions on the same data."""

    __tablename__ = "ab_test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_a_id: Mapped[int | None] = mapped_column(nullable=True)
    strategy_b_id: Mapped[int | None] = mapped_column(nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT")
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    winner: Mapped[str] = mapped_column(String(16), default="TIE")  # A | B | TIE
    a_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    b_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    a_fitness: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    b_fitness: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    p_value: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("1"))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
