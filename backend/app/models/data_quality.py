from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class MarketDataRaw(Base):
    """Unmodified candle exactly as received from the exchange feed."""

    __tablename__ = "market_data_raw"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", "source", name="uq_mdq_raw"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_type: Mapped[str] = mapped_column(String(16), default="OHLCV")
    open: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    high: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    low: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    volume: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(32), default="gateio")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class MarketDataClean(Base):
    """Validated/normalized candle emitted to downstream consumers."""

    __tablename__ = "market_data_clean"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", "source", name="uq_mdq_clean"),
    )

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
    repair_action: Mapped[str] = mapped_column(String(32), default="NONE")  # NONE|DROP|INTERPOLATE|...
    is_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    health_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class MarketDataAnomaly(Base):
    """A single detected anomaly / validation failure on a candle."""

    __tablename__ = "market_data_anomalies"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="WARNING")  # INFO|WARNING|CRITICAL
    detection_method: Mapped[str] = mapped_column(String(32), default="rule")
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(24, 10), nullable=True)
    repair_action: Mapped[str] = mapped_column(String(32), default="NONE")
    detail: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="gateio")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class MarketDataHealthLog(Base):
    """Time series of the rolling data health score per symbol/timeframe."""

    __tablename__ = "market_data_health_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    health_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    consistency_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    completeness_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    anomaly_inverse_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    latency_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))
    category: Mapped[str] = mapped_column(String(16), default="EXCELLENT")
    trade_status: Mapped[str] = mapped_column(String(16), default="CLEAN")
    candles_evaluated: Mapped[int] = mapped_column(default=0)
    anomalies_found: Mapped[int] = mapped_column(default=0)
    missing_candles: Mapped[int] = mapped_column(default=0)
    feed_latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class DataQualityReport(Base):
    """Aggregated quality report over a window for a symbol/timeframe."""

    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_candles: Mapped[int] = mapped_column(default=0)
    valid_candles: Mapped[int] = mapped_column(default=0)
    anomalies_total: Mapped[int] = mapped_column(default=0)
    missing_candles: Mapped[int] = mapped_column(default=0)
    average_health_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    category: Mapped[str] = mapped_column(String(16), default="EXCELLENT")
    anomaly_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    report_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
