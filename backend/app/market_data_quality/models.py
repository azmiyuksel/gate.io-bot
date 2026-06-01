"""Domain types, enums and constants for the Market Data Quality engine.

Kept local to the module (mirroring ``execution_quality.models``) so the quality
vocabulary lives next to the logic that uses it. Persistence-layer enums are
stored as plain strings on the entities, so these classes are the single source
of truth for the allowed values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class DataQualityCategory(StrEnum):
    excellent = "EXCELLENT"      # 90 - 100
    good = "GOOD"                # 75 - 89
    risky = "RISKY"              # 50 - 74
    unreliable = "UNRELIABLE"    # < 50


class DataTradeStatus(StrEnum):
    """How the live/paper engine should treat the current data feed."""

    clean = "CLEAN"          # normal trading
    degraded = "DEGRADED"    # trade with reduced risk
    invalid = "INVALID"      # pause trading


class AnomalyType(StrEnum):
    price_spike = "PRICE_SPIKE"
    volume_spike = "VOLUME_SPIKE"
    flash_crash = "FLASH_CRASH"
    flash_pump = "FLASH_PUMP"
    liquidity_drop = "LIQUIDITY_DROP"
    candle_gap = "CANDLE_GAP"
    ohlc_inconsistency = "OHLC_INCONSISTENCY"
    invalid_value = "INVALID_VALUE"
    duplicate_timestamp = "DUPLICATE_TIMESTAMP"
    cross_exchange_divergence = "CROSS_EXCHANGE_DIVERGENCE"
    isolation_forest = "ISOLATION_FOREST_OUTLIER"


class RepairAction(StrEnum):
    none = "NONE"
    drop = "DROP"
    interpolate = "INTERPOLATE"
    last_valid = "LAST_VALID"
    flag_uncertain = "FLAG_UNCERTAIN"


class ValidationCode(StrEnum):
    ok = "OK"
    high_below_components = "HIGH_BELOW_COMPONENTS"
    low_above_components = "LOW_ABOVE_COMPONENTS"
    non_positive_price = "NON_POSITIVE_PRICE"
    negative_volume = "NEGATIVE_VOLUME"
    duplicate_timestamp = "DUPLICATE_TIMESTAMP"
    excessive_move = "EXCESSIVE_MOVE"
    missing_field = "MISSING_FIELD"


class DataType(StrEnum):
    ohlcv = "OHLCV"
    tick = "TICK"
    order_book = "ORDER_BOOK"
    market_stats = "MARKET_STATS"


# Data health score weights (sum to 1.0). See data_health_score.py.
CONSISTENCY_WEIGHT = 0.30
COMPLETENESS_WEIGHT = 0.30
ANOMALY_INVERSE_WEIGHT = 0.20
LATENCY_WEIGHT = 0.20

# Category thresholds.
EXCELLENT_THRESHOLD = 90.0
GOOD_THRESHOLD = 75.0
RISKY_THRESHOLD = 50.0

# Trading gate: minimum health score to allow normal trading.
DEGRADED_THRESHOLD = 75.0  # below this -> degraded (reduced risk)
INVALID_THRESHOLD = 50.0   # below this -> invalid (pause)


def category_for_score(score: float) -> DataQualityCategory:
    if score >= EXCELLENT_THRESHOLD:
        return DataQualityCategory.excellent
    if score >= GOOD_THRESHOLD:
        return DataQualityCategory.good
    if score >= RISKY_THRESHOLD:
        return DataQualityCategory.risky
    return DataQualityCategory.unreliable


def trade_status_for_score(score: float) -> DataTradeStatus:
    if score >= DEGRADED_THRESHOLD:
        return DataTradeStatus.clean
    if score >= INVALID_THRESHOLD:
        return DataTradeStatus.degraded
    return DataTradeStatus.invalid


@dataclass
class CandleData:
    """Normalized in-memory representation of a single OHLCV candle."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = "gateio"

    def to_floats(self) -> dict[str, float]:
        return {
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }


@dataclass
class AnomalyFinding:
    anomaly_type: AnomalyType
    severity: str               # INFO | WARNING | CRITICAL
    detail: str
    observed_value: float | None = None
    threshold_value: float | None = None
    detection_method: str = "rule"


@dataclass
class ValidationResult:
    is_valid: bool
    codes: list[ValidationCode] = field(default_factory=list)
    details: list[str] = field(default_factory=list)

    def add(self, code: ValidationCode, detail: str) -> None:
        self.is_valid = False
        self.codes.append(code)
        self.details.append(detail)


@dataclass
class HealthScore:
    score: float
    consistency_score: float
    completeness_score: float
    anomaly_inverse_score: float
    latency_score: float
    category: DataQualityCategory
    trade_status: DataTradeStatus


@dataclass
class QualityResult:
    """Outcome of running a candle through the full pipeline."""

    candle: CandleData
    validation: ValidationResult
    anomalies: list[AnomalyFinding]
    repair_action: RepairAction
    is_clean: bool
    cleaned_candle: CandleData | None
