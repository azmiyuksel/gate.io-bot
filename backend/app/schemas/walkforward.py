from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class WalkForwardStart(BaseModel):
    strategy_name: str = "momentum_breakout_v1"
    symbol: str
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    mode: Literal["rolling", "expanding"] = "rolling"
    start_at: datetime
    end_at: datetime
    train_period_days: int = 365
    test_period_days: int = 90
    step_days: int = 90
    n_trials: int = Field(default=30, ge=1, le=500)
    initial_cash: Decimal = Decimal("10000")
    data_source: Literal["cache", "gateio", "csv"] = "cache"
    csv_data: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class WalkForwardListItem(BaseModel):
    id: int
    created_at: datetime
    strategy_name: str
    symbol: str
    timeframe: str
    mode: str
    status: str
    robustness_score: float = 0
    wfe: float = 0
    consistency_score: float = 0
    average_sharpe: float = 0
    average_drawdown: float = 0
    deployment_decision: str = "AUTO_DEPLOYMENT_REJECT"


class WalkForwardDetail(BaseModel):
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    mode: str
    status: str
    parameters: dict[str, Any]
    aggregated_metrics: dict[str, Any]
    combined_equity_curve: list[dict[str, Any]]
    monte_carlo_results: dict[str, Any]
    deployment_decision: dict[str, Any]
    overfit_warnings: list[Any]
    report: dict[str, Any]
    windows: list[dict[str, Any]]
