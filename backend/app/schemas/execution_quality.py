from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from typing import Dict, List, Optional


class ExecutionQualityStatusOut(BaseModel):
    strategy_name: str
    execution_quality_score: Decimal
    slippage_avg: Decimal
    slippage_std: Decimal
    latency_total_execution_ms: Decimal
    fill_completion_rate: Decimal
    partial_fill_ratio: Decimal
    quality_category: str
    anomaly_status: str
    anomaly_reason: str


class ExecutionSlippageOut(BaseModel):
    id: int
    execution_order_id: int
    slippage_pct: Decimal
    slippage_category: str
    volatility_rolling: Decimal
    spread: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class ExecutionLatencyOut(BaseModel):
    id: int
    execution_order_id: int
    signal_to_submit_ms: int
    submit_to_ack_ms: int
    ack_to_fill_ms: int
    total_execution_delay_ms: int
    created_at: datetime

    class Config:
        from_attributes = True


class ExecutionReportOut(BaseModel):
    id: int
    strategy_name: str
    start_time: datetime
    end_time: datetime
    total_orders: int
    total_fills: int
    average_slippage_pct: Decimal
    average_latency_ms: Decimal
    average_quality_score: Decimal
    sharpe_decay: Decimal
    slippage_cost_usd: Decimal
    report_data: dict
    created_at: datetime

    class Config:
        from_attributes = True
