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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class LearningCycle(Base):
    """One run of the continuous learning loop."""

    __tablename__ = "learning_cycles"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT")
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    patterns_found: Mapped[int] = mapped_column(default=0)
    hypotheses_generated: Mapped[int] = mapped_column(default=0)
    features_discovered: Mapped[int] = mapped_column(default=0)
    strategies_evolved: Mapped[int] = mapped_column(default=0)
    strategies_validated: Mapped[int] = mapped_column(default=0)
    promotion_requests: Mapped[int] = mapped_column(default=0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeEntry(Base):
    """A learned fact: pattern, failure, regime, portfolio or meta insight."""

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    knowledge_type: Mapped[str] = mapped_column(String(16), default="PATTERN", index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT", index=True)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.5"))
    support: Mapped[int] = mapped_column(default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    cycle_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_cycles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class DiscoveredFeature(Base):
    """A derived feature combination discovered and auto-tested by the system."""

    __tablename__ = "discovered_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    formula: Mapped[str] = mapped_column(String(255))
    symbol: Mapped[str] = mapped_column(String(32), default="BTC_USDT", index=True)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    correlation_with_profit: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    importance_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    stability_score: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    cycle_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_cycles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class StrategyRanking(Base):
    """Weighted 0-100 ranking of an evolved strategy version."""

    __tablename__ = "strategy_rankings"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(index=True)
    version_id: Mapped[int | None] = mapped_column(nullable=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), index=True)
    robustness: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    walk_forward: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    stability: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    sharpe: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    drawdown: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    cycle_id: Mapped[int | None] = mapped_column(
        ForeignKey("learning_cycles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class PromotionRequest(Base):
    """Human-in-the-loop promotion workflow. APPROVED only via explicit human action."""

    __tablename__ = "promotion_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(index=True)
    version_id: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="AWAITING_VALIDATION", index=True)
    ranking_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    gate_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    gate_reasons: Mapped[list] = mapped_column(JSON, default=list)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by: Mapped[str] = mapped_column(String(64), default="auto_learning")
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningReport(Base):
    """Periodic (e.g. weekly) learning report."""

    __tablename__ = "learning_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    patterns_learned: Mapped[int] = mapped_column(default=0)
    failed_strategies: Mapped[int] = mapped_column(default=0)
    new_candidates: Mapped[int] = mapped_column(default=0)
    promotion_requests: Mapped[int] = mapped_column(default=0)
    report_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
