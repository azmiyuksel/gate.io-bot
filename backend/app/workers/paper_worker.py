import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.entities import PaperAccount
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.strategy_adapter import CapitalPreservationAdapter
from app.services.exchange.gateio import GateIOClient

logger = logging.getLogger(__name__)


async def prewarm_strategy(strategy: CapitalPreservationAdapter, symbols: list[str]) -> None:
    client = GateIOClient()
    for symbol in symbols:
        try:
            candles = await client.candles(symbol, interval="1h", limit=200)
            if candles:
                strategy.prewarm_candles(symbol, candles)
                logger.info("Pre-warmed %s with %d candles", symbol, len(candles))
        except Exception as exc:
            logger.warning("Failed to pre-warm %s: %s", symbol, exc)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    db = SessionLocal()
    try:
        account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
        if account is None:
            account = PaperAccount()
            db.add(account)
            db.commit()
            db.refresh(account)
        strategy = CapitalPreservationAdapter(candle_window=2, min_candles=200)
        logger.info("Pre-warming strategy with historical candles...")
        await prewarm_strategy(strategy, settings.symbols)
        engine = PaperTradingEngine(db, account, strategy=strategy)
        await engine.start(settings.symbols)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
