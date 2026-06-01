from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from typing import Dict, List, Optional


class StrategyHealthOut(BaseModel):
    health_score: Decimal
    drift_score: Decimal
    state: str
    failure_mode: str
    anomaly: str


class StrategyBaselineOut(BaseModel):
    id: int
    strategy_name: str
    expected_sharpe: Decimal
    expected_win_rate: Decimal
    expected_profit_factor: Decimal
    expected_drawdown: Decimal
    expected_trade_frequency: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class StrategyHealthLogOut(BaseModel):
    id: int
    strategy_name: str
    rolling_sharpe: Decimal
    rolling_win_rate: Decimal
    rolling_profit_factor: Decimal
    rolling_drawdown: Decimal
    expectancy: Decimal
    health_score: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyAlertOut(BaseModel):
    id: int
    strategy_name: str
    alert_level: str
    message: str
    action_taken: str
    created_at: datetime

    class Config:
        from_attributes = True


class StrategyStateHistoryOut(BaseModel):
    id: int
    strategy_name: str
    old_state: str
    new_state: str
    trigger_reason: str
    created_at: datetime

    class Config:
        from_attributes = True
