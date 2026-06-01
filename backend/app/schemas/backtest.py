from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class BacktestCreate(BaseModel):
    strategy_name: str = "ema_rsi_atr_v1"
    symbol: str
    timeframe: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1h"
    start_at: datetime
    end_at: datetime
    initial_cash: Decimal = Decimal("10000")
    data_source: Literal["cache", "gateio", "csv"] = "cache"
    csv_data: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestListItem(BaseModel):
    id: int
    created_at: datetime
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    net_profit: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0


class BacktestDetail(BaseModel):
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    parameters: dict[str, Any]
    metrics: dict[str, Any]
    charts: dict[str, Any]
    optimization_results: list[Any]
    walk_forward_results: list[Any]
    monte_carlo_results: dict[str, Any]
    trades: list[dict[str, Any]]


class OptimizationRequest(BaseModel):
    grid: dict[str, list[Any]] = Field(
        default_factory=lambda: {
            "ema_trend": [100, 150, 200],
            "rsi_threshold": [25, 30, 35],
            "atr_multiplier": [1.5, 2.0, 2.5],
        }
    )


class WalkForwardRequest(BaseModel):
    windows: list[dict[str, datetime]] = Field(
        default_factory=lambda: [
            {
                "train_start": datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
                "train_end": datetime.fromisoformat("2023-12-31T23:59:59+00:00"),
                "test_start": datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
                "test_end": datetime.fromisoformat("2024-12-31T23:59:59+00:00"),
            },
            {
                "train_start": datetime.fromisoformat("2023-01-01T00:00:00+00:00"),
                "train_end": datetime.fromisoformat("2024-12-31T23:59:59+00:00"),
                "test_start": datetime.fromisoformat("2025-01-01T00:00:00+00:00"),
                "test_end": datetime.fromisoformat("2025-12-31T23:59:59+00:00"),
            },
        ]
    )
    grid: dict[str, list[Any]] = Field(
        default_factory=lambda: {
            "ema_trend": [100, 150, 200],
            "rsi_threshold": [25, 30, 35],
            "atr_multiplier": [1.5, 2.0, 2.5],
        }
    )
