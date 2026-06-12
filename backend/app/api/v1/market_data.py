from typing import List

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, current_user_role, require_admin
from app.core.config import get_settings
from app.market_data.ingestion import MarketDataIngestion
from app.market_data.price_cache import price_cache
from app.models.entities import HistoricalCandle
from app.schemas.market_data import CandleOut, IngestionResultOut, LatestPriceOut
from app.services.exchange.gateio import GateIOClient
from app.schemas._common import _validate_symbol, _validate_timeframe

router = APIRouter(
    prefix="/market-data", tags=["market-data"], dependencies=[Depends(current_user_role)]
)


@router.get("/candles", response_model=List[CandleOut])
def candles(
    symbol: str = Query(..., description="Trading pair symbol (e.g. BTC_USDT)"),
    db: DbSession = None,
    interval: str = Query("1h", description="Candle timeframe"),
    limit: int = Query(240, ge=1, le=1000),
) -> List[HistoricalCandle]:
    _validate_symbol(symbol)
    _validate_timeframe(interval)
    rows = (
        db.query(HistoricalCandle)
        .filter(HistoricalCandle.symbol == symbol)
        .filter(HistoricalCandle.timeframe == interval)
        .order_by(HistoricalCandle.timestamp.desc())
        .limit(min(limit, 1000))
        .all()
    )
    return list(reversed(rows))


@router.get("/latest", response_model=LatestPriceOut)
def latest() -> LatestPriceOut:
    return LatestPriceOut(prices=price_cache.snapshot())


@router.post("/ingest", response_model=IngestionResultOut, dependencies=[Depends(require_admin)])
async def ingest(db: DbSession, interval: str | None = None) -> IngestionResultOut:
    settings = get_settings()
    client = GateIOClient()
    try:
        inserted = await MarketDataIngestion(db, client).ingest_all(settings.symbols, interval)
    finally:
        await client.close()
    return IngestionResultOut(inserted=inserted)
