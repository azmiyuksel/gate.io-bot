from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from typing import Dict, Optional


class RegimeStatusOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    regime_type: str
    confidence: Decimal
    rule_based_vote: str
    clustering_vote: str
    ml_vote: str
    created_at: datetime

    class Config:
        from_attributes = True


class RegimeTransitionOut(BaseModel):
    id: int
    symbol: str
    old_regime: str
    new_regime: str
    confidence: Decimal
    trigger_event: str
    created_at: datetime

    class Config:
        from_attributes = True


class RegimeConfidenceOut(BaseModel):
    id: int
    symbol: str
    timestamp: datetime
    confidence_score: Decimal
    vote_weights: Dict[str, float]

    class Config:
        from_attributes = True


class RegimePerformanceOut(BaseModel):
    id: int
    regime_type: str
    strategy_name: str
    total_trades: int
    winning_trades: int
    profit_factor: Decimal
    total_pnl: Decimal
    drawdown: Decimal
    updated_at: datetime

    class Config:
        from_attributes = True


class RegimeRecalculateRequest(BaseModel):
    symbol: str = "BTC_USDT"
    timeframe: str = "1h"
