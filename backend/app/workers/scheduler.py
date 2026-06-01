import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.account.engine import AccountManager
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.market_data.ingestion import MarketDataIngestion
from app.market_data.websocket import GateIOWebSocketClient
from app.reconciliation.engine import ReconciliationEngine
from app.repositories.trading import StrategySettingsRepository
from app.services.exchange.gateio import GateIOClient
from app.services.notifications.telegram import TelegramNotifier
from app.services.risk.circuit_breaker import CircuitBreaker
from app.services.trading_engine import TradingEngine


async def run_cycle() -> None:
    settings = get_settings()
    db = SessionLocal()
    client = GateIOClient()
    try:
        # 1. Always reconcile open orders with the exchange first.
        await ReconciliationEngine(db, client).reconcile_open_orders()

        # 2. Mark the account to market and derive real equity.
        snapshot = await AccountManager(db, client).refresh()
        equity = snapshot.total_equity

        # 3. Global kill-switch: trip on breached limits, halt cycle if tripped.
        breaker = CircuitBreaker(db)
        drawdown = AccountManager(db).drawdown_pct()
        if breaker.check_and_trip(equity, drawdown):
            return

        strategy_settings = StrategySettingsRepository(db).current()
        if not strategy_settings.is_enabled:
            return

        engine = TradingEngine(db, client)
        await engine.manage_open_positions()
        for symbol in settings.symbols:
            await engine.scan_symbol(symbol, equity)
    finally:
        await client.close()
        db.close()


async def ingest_market_data() -> None:
    settings = get_settings()
    db = SessionLocal()
    client = GateIOClient()
    try:
        await MarketDataIngestion(db, client).ingest_all(settings.symbols)
    finally:
        await client.close()
        db.close()


async def startup_recovery() -> None:
    """Realign local order/position state with the exchange after a restart."""
    db = SessionLocal()
    client = GateIOClient()
    try:
        await ReconciliationEngine(db, client).recover_on_startup()
    finally:
        await client.close()
        db.close()


async def daily_report() -> None:
    await TelegramNotifier().send("Daily report: check dashboard for PnL, drawdown and open risk.")


async def main() -> None:
    settings = get_settings()
    await startup_recovery()

    # Stream live prices into the shared cache in the background.
    ws_client = GateIOWebSocketClient(settings.symbols)
    ws_task = asyncio.create_task(ws_client.run())

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_cycle, "interval", minutes=15, max_instances=1)
    scheduler.add_job(ingest_market_data, "interval", minutes=15, max_instances=1)
    scheduler.add_job(daily_report, "cron", hour=21, minute=0)
    scheduler.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        ws_client.stop()
        ws_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
