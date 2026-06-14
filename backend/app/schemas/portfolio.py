from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class PortfolioCreate(BaseModel):
    name: str = Field(default="default")
    description: Optional[str] = None
    initial_balance: Decimal = Field(default=Decimal("10000.0"))
    daily_max_risk_pct: Decimal = Field(default=Decimal("0.02"))
    weekly_max_risk_pct: Decimal = Field(default=Decimal("0.05"))
    monthly_max_risk_pct: Decimal = Field(default=Decimal("0.10"))


class PortfolioAssetOut(BaseModel):
    id: int
    symbol: str
    position_size: Decimal
    average_entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    risk_contribution: Decimal
    updated_at: datetime

    class Config:
        from_attributes = True


class AllocationOut(BaseModel):
    id: int
    target_type: str
    target_name: str
    weight: Decimal
    allocated_amount: Decimal
    performance_score: Decimal
    risk_adjusted_return: Decimal
    correlation_penalty: Decimal
    stability_score: Decimal
    drawdown_adjustment: Decimal

    class Config:
        from_attributes = True


class RebalanceOut(BaseModel):
    id: int
    trigger_reason: str
    previous_weights: Dict[str, float]
    new_weights: Dict[str, float]
    execution_log: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class PortfolioMetricOut(BaseModel):
    id: int
    timestamp: datetime
    total_equity: Decimal
    sharpe_ratio: Decimal
    drawdown: Decimal
    correlation_risk_score: Decimal
    exposure_per_asset: Dict[str, float]
    exposure_per_strategy: Dict[str, float]
    volatility_adjusted_return: Decimal

    class Config:
        from_attributes = True


class RiskSnapshotOut(BaseModel):
    id: int
    timestamp: datetime
    scenario_name: str
    simulated_loss: Decimal
    limit_status: str
    metrics_snapshot: Dict[str, Any] = {}

    class Config:
        from_attributes = True
        arbitrary_types_allowed = True


class PortfolioOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    total_equity: Decimal
    cash_balance: Decimal
    peak_equity: Decimal
    daily_max_risk_pct: Decimal
    weekly_max_risk_pct: Decimal
    monthly_max_risk_pct: Decimal
    created_at: datetime
    updated_at: datetime
    assets: List[PortfolioAssetOut] = []
    allocations: List[AllocationOut] = []

    class Config:
        from_attributes = True
