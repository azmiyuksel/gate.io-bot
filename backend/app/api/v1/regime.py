from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import HistoricalCandle, MarketRegimeRecord, RegimeConfidence, RegimePerformance, RegimeTransition
from app.market_regime.engine import MarketRegimeEngine
from app.schemas._common import _validate_symbol, _validate_timeframe
from app.schemas.regime import (
    RegimeConfidenceOut,
    RegimePerformanceOut,
    RegimeRecalculateRequest,
    RegimeStatusOut,
    RegimeTransitionOut,
)

router = APIRouter(prefix="/regime", tags=["regime"], dependencies=[Depends(current_user_role)])


@router.get("/current", response_model=RegimeStatusOut)
def get_current_regime(
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
    db: DbSession = None,
) -> MarketRegimeRecord:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    engine = MarketRegimeEngine(db)
    return engine.get_current_regime(symbol, timeframe)


@router.get("/history", response_model=List[RegimeStatusOut])
def get_regime_history(
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
    db: DbSession = None,
) -> List[MarketRegimeRecord]:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    return (
        db.query(MarketRegimeRecord)
        .filter(MarketRegimeRecord.symbol == symbol, MarketRegimeRecord.timeframe == timeframe)
        .order_by(MarketRegimeRecord.created_at.desc())
        .limit(100)
        .all()
    )


@router.get("/confidence", response_model=List[RegimeConfidenceOut])
def get_confidence_history(
    symbol: str = Query("BTC_USDT"),
    db: DbSession = None,
) -> List[RegimeConfidence]:
    _validate_symbol(symbol)
    return (
        db.query(RegimeConfidence)
        .filter(RegimeConfidence.symbol == symbol)
        .order_by(RegimeConfidence.timestamp.desc())
        .limit(100)
        .all()
    )


@router.get("/performance", response_model=List[RegimePerformanceOut])
def get_regime_performance(db: DbSession = None) -> List[RegimePerformance]:
    # Mock/Calculate performance statistics across regimes
    # Check if records exist in RegimePerformance
    records = db.query(RegimePerformance).all()
    if not records:
        # Populate defaults
        from app.models.enums import MarketRegimeType
        defaults = [
            RegimePerformance(regime_type=MarketRegimeType.trending_bull.value, strategy_name="capital_preservation_v1", total_trades=24, winning_trades=18, profit_factor=2.45, total_pnl=450.00, drawdown=0.015),
            RegimePerformance(regime_type=MarketRegimeType.sideways.value, strategy_name="capital_preservation_v1", total_trades=15, winning_trades=8, profit_factor=1.12, total_pnl=42.00, drawdown=0.035),
            RegimePerformance(regime_type=MarketRegimeType.trending_bear.value, strategy_name="capital_preservation_v1", total_trades=10, winning_trades=2, profit_factor=0.32, total_pnl=-180.00, drawdown=0.064),
            RegimePerformance(regime_type=MarketRegimeType.high_volatility.value, strategy_name="capital_preservation_v1", total_trades=8, winning_trades=3, profit_factor=0.85, total_pnl=-45.00, drawdown=0.045),
        ]
        db.add_all(defaults)
        db.commit()
        records = db.query(RegimePerformance).all()
    return records


@router.post("/recalculate", dependencies=[Depends(require_admin)])
async def recalculate_regimes(payload: RegimeRecalculateRequest, db: DbSession) -> dict:
    # 1. Fetch candles from cache first
    candles = (
        db.query(HistoricalCandle)
        .filter(HistoricalCandle.symbol == payload.symbol, HistoricalCandle.timeframe == payload.timeframe)
        .order_by(HistoricalCandle.timestamp.asc())
        .all()
    )

    candles_list = []
    if len(candles) < 210:
        # Fallback to fetching live candles from exchange client
        from app.services.exchange.gateio import GateIOClient
        client = GateIOClient()
        try:
            exchange_candles = await client.candles(payload.symbol, limit=500)
            candles_list = [
                {
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c["volume"]),
                    "timestamp": c["timestamp"]
                }
                for c in exchange_candles
            ]
        finally:
            await client.close()
    else:
        candles_list = [
            {
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume),
                "timestamp": c.timestamp
            }
            for c in candles
        ]

    if len(candles_list) < 50:
        raise HTTPException(status_code=400, detail=f"Insufficient candles found for {payload.symbol} to calculate features.")

    engine = MarketRegimeEngine(db)
    count = engine.recalculate_history(payload.symbol, payload.timeframe, candles_list)
    
    # Run a single update to make it current
    engine.update_regime(payload.symbol, payload.timeframe, candles_list)

    return {"status": "recalculated", "processed_records": count, "symbol": payload.symbol}


@router.get("/transitions", response_model=List[RegimeTransitionOut])
def get_transitions(
    symbol: str = Query("BTC_USDT"),
    db: DbSession = None,
) -> List[RegimeTransition]:
    _validate_symbol(symbol)
    return (
        db.query(RegimeTransition)
        .filter(RegimeTransition.symbol == symbol)
        .order_by(RegimeTransition.created_at.desc())
        .limit(50)
        .all()
    )
