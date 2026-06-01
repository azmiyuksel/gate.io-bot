from typing import List

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, current_user_role, require_admin
from app.core.config import get_settings
from app.market_data.ingestion import MarketDataIngestion
from app.market_data.price_cache import price_cache
from app.models.entities import HistoricalCandle
from app.schemas.market_data import CandleOut, IngestionResultOut, LatestPriceOut
from app.services.exchange.gateio import GateIOClient

router = APIRouter(
    prefix="/market-data", tags=["market-data"], dependencies=[Depends(current_user_role)]
)


@router.get("/candles", response_model=List[CandleOut])
def candles(symbol: str, db: DbSession, interval: str = "1h", limit: int = 240) -> List[HistoricalCandle]:
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
