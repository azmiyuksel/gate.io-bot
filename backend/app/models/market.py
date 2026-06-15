from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import MarketRegimeType


def now_utc() -> datetime:
    return datetime.now(UTC)


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
