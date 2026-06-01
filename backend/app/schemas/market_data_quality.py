from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DataQualityStatusOut(BaseModel):
    symbol: str
    timeframe: str
    health_score: Decimal
    category: str
    trade_status: str
    consistency_score: Decimal
    completeness_score: Decimal
    anomaly_inverse_score: Decimal
    latency_score: Decimal
    candles_evaluated: int
    anomalies_found: int
    missing_candles: int
    feed_latency_ms: Decimal
    updated_at: datetime | None = None


class DataQualityScoreOut(BaseModel):
    symbol: str
    timeframe: str
    health_score: Decimal
    category: str
    trade_status: str


class MarketDataAnomalyOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    timestamp: datetime
    anomaly_type: str
    severity: str
    detection_method: str
    observed_value: Decimal | None
    threshold_value: Decimal | None
    repair_action: str
    detail: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class MarketDataHealthLogOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    health_score: Decimal
    consistency_score: Decimal
    completeness_score: Decimal
    anomaly_inverse_score: Decimal
    latency_score: Decimal
    category: str
    trade_status: str
    candles_evaluated: int
    anomalies_found: int
    missing_candles: int
    feed_latency_ms: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class DataQualityReportOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    start_time: datetime
    end_time: datetime
    total_candles: int
    valid_candles: int
    anomalies_total: int
    missing_candles: int
    average_health_score: Decimal
    category: str
    anomaly_breakdown: dict
    created_at: datetime

    class Config:
        from_attributes = True


class RevalidateIn(BaseModel):
    symbol: str
    timeframe: str = "1h"
    limit: int = 240


class RevalidateOut(BaseModel):
    symbol: str
    timeframe: str
    total: int
    valid: int
    clean_emitted: int
    anomalies: int
    missing_candles: int
    health_score: Decimal
    category: str
    trade_status: str
