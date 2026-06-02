from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession, current_user_role, require_admin
from app.core.config import get_settings
from app.market_data_quality.engine import MarketDataQualityEngine
from app.market_data_quality.models import trade_status_for_score
from app.models.entities import MarketDataAnomaly, MarketDataHealthLog
from app.schemas.market_data_quality import (
    DataQualityReportOut,
    DataQualityScoreOut,
    DataQualityStatusOut,
    MarketDataAnomalyOut,
    MarketDataHealthLogOut,
    RevalidateIn,
    RevalidateOut,
)
from app.services.exchange.gateio import GateIOClient

router = APIRouter(
    prefix="/data-quality", tags=["data-quality"], dependencies=[Depends(current_user_role)]
)


def _latest_health(db, symbol: str, timeframe: str) -> MarketDataHealthLog:
    log = (
        db.query(MarketDataHealthLog)
        .filter(MarketDataHealthLog.symbol == symbol)
        .filter(MarketDataHealthLog.timeframe == timeframe)
        .order_by(MarketDataHealthLog.created_at.desc())
        .first()
    )
    if log is None:
        raise HTTPException(status_code=404, detail="No data quality health for symbol/timeframe")
    return log


@router.get("/status", response_model=DataQualityStatusOut)
def status(symbol: str, db: DbSession, timeframe: str = "1h") -> DataQualityStatusOut:
    log = _latest_health(db, symbol, timeframe)
    return DataQualityStatusOut(
        symbol=log.symbol,
        timeframe=log.timeframe,
        health_score=log.health_score,
        category=log.category,
        trade_status=log.trade_status,
        consistency_score=log.consistency_score,
        completeness_score=log.completeness_score,
        anomaly_inverse_score=log.anomaly_inverse_score,
        latency_score=log.latency_score,
        candles_evaluated=log.candles_evaluated,
        anomalies_found=log.anomalies_found,
        missing_candles=log.missing_candles,
        feed_latency_ms=log.feed_latency_ms,
        updated_at=log.created_at,
    )


@router.get("/score", response_model=DataQualityScoreOut)
def score(symbol: str, db: DbSession, timeframe: str = "1h") -> DataQualityScoreOut:
    log = _latest_health(db, symbol, timeframe)
    return DataQualityScoreOut(
        symbol=log.symbol,
        timeframe=log.timeframe,
        health_score=log.health_score,
        category=log.category,
        trade_status=log.trade_status,
    )


@router.get("/anomalies", response_model=List[MarketDataAnomalyOut])
def anomalies(
    symbol: str, db: DbSession, timeframe: str = "1h", limit: int = 100
) -> List[MarketDataAnomaly]:
    return (
        db.query(MarketDataAnomaly)
        .filter(MarketDataAnomaly.symbol == symbol)
        .filter(MarketDataAnomaly.timeframe == timeframe)
        .order_by(MarketDataAnomaly.created_at.desc())
        .limit(min(limit, 1000))
        .all()
    )


@router.get("/health-logs", response_model=List[MarketDataHealthLogOut])
def health_logs(
    symbol: str, db: DbSession, timeframe: str = "1h", limit: int = 200
) -> List[MarketDataHealthLog]:
    rows = (
        db.query(MarketDataHealthLog)
        .filter(MarketDataHealthLog.symbol == symbol)
        .filter(MarketDataHealthLog.timeframe == timeframe)
        .order_by(MarketDataHealthLog.created_at.desc())
        .limit(min(limit, 1000))
        .all()
    )
    return list(reversed(rows))


@router.get("/report", response_model=DataQualityReportOut)
def report(
    symbol: str, db: DbSession, timeframe: str = "1h", hours: int = 24
) -> DataQualityReportOut:
    end = datetime.now(UTC)
    start = end - timedelta(hours=hours)
    return MarketDataQualityEngine(db).generate_report(symbol, timeframe, start, end, persist=False)


@router.post("/revalidate", response_model=RevalidateOut, dependencies=[Depends(require_admin)])
async def revalidate(payload: RevalidateIn, db: DbSession) -> RevalidateOut:
    # Clamp the client-supplied limit to bound memory and Gate.io API abuse.
    safe_limit = min(max(payload.limit, 1), get_settings().max_query_limit)
    client = GateIOClient()
    try:
        candles = await client.candles(
            payload.symbol, interval=payload.timeframe, limit=safe_limit
        )
    finally:
        await client.close()

    result = MarketDataQualityEngine(db).ingest(
        candles, payload.symbol, payload.timeframe, source="gateio"
    )
    score_value = result.health.score
    return RevalidateOut(
        symbol=result.symbol,
        timeframe=result.timeframe,
        total=result.total,
        valid=result.valid,
        clean_emitted=result.clean_emitted,
        anomalies=result.anomalies,
        missing_candles=result.missing_candles,
        health_score=Decimal(str(score_value)),
        category=str(result.health.category),
        trade_status=str(trade_status_for_score(score_value)),
    )
