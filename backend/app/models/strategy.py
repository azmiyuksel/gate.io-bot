from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.enums import StrategyAlertLevel, StrategyHealthState


def now_utc() -> datetime:
    return datetime.now(UTC)


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
