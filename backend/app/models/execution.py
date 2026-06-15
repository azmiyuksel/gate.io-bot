from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    JSON,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class ExecutionOrder(Base):
    __tablename__ = "execution_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    paper_order_id: Mapped[int | None] = mapped_column(ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(16))
    order_type: Mapped[str] = mapped_column(String(32), default="market")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    expected_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    expected_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    signal_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submission_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ExecutionFill(Base):
    __tablename__ = "execution_fills"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_order_id: Mapped[int] = mapped_column(ForeignKey("execution_orders.id", ondelete="CASCADE"))
    fill_price: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fill_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slippage: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ExecutionMetric(Base):
    __tablename__ = "execution_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    slippage_avg: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    slippage_std: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    latency_signal_submit_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    latency_submit_ack_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    latency_ack_fill_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    latency_total_execution_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    fill_completion_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    partial_fill_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    execution_quality_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("100.0"))


class SlippageLog(Base):
    __tablename__ = "slippage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_order_id: Mapped[int] = mapped_column(ForeignKey("execution_orders.id", ondelete="CASCADE"))
    slippage_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    slippage_category: Mapped[str] = mapped_column(String(32))  # GOOD | NORMAL | BAD | CRITICAL
    volatility_rolling: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    spread: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class LatencyLog(Base):
    __tablename__ = "latency_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    execution_order_id: Mapped[int] = mapped_column(ForeignKey("execution_orders.id", ondelete="CASCADE"))
    signal_generation_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order_submission_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    exchange_ack_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fill_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_to_submit_ms: Mapped[int] = mapped_column(default=0)
    submit_to_ack_ms: Mapped[int] = mapped_column(default=0)
    ack_to_fill_ms: Mapped[int] = mapped_column(default=0)
    total_execution_delay_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)


class ExecutionReport(Base):
    __tablename__ = "execution_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_orders: Mapped[int] = mapped_column(default=0)
    total_fills: Mapped[int] = mapped_column(default=0)
    average_slippage_pct: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    average_latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    average_quality_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"))
    sharpe_decay: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    slippage_cost_usd: Mapped[Decimal] = mapped_column(Numeric(24, 10), default=Decimal("0"))
    report_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
