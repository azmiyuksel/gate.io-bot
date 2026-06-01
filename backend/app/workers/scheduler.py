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
        await _alert_on_degraded_feeds(db, settings.symbols)
    finally:
        await client.close()
        db.close()


async def _alert_on_degraded_feeds(db, symbols: list[str]) -> None:
    """Notify when any symbol's data feed health is degraded or invalid."""
    from app.market_data_quality.engine import MarketDataQualityEngine
    from app.market_data_quality.models import DataTradeStatus

    engine = MarketDataQualityEngine(db)
    notifier = TelegramNotifier()
    for symbol in symbols:
        log = engine.latest_health(symbol, get_settings().market_data_interval)
        if log is None:
            continue
        status = log.trade_status
        if status in (DataTradeStatus.degraded, DataTradeStatus.invalid):
            await notifier.send(
                f"⚠️ Veri Kalite Uyarisi: {symbol} feed {status} "
                f"(health={log.health_score}, anomalies={log.anomalies_found})"
            )


async def startup_recovery() -> None:
    """Realign local order/position state with the exchange after a restart."""
    db = SessionLocal()
    client = GateIOClient()
    try:
        await ReconciliationEngine(db, client).recover_on_startup()
    finally:
        await client.close()
        db.close()


async def run_research_loop() -> None:
    """Continuous strategy research: evolve a generation and alert on promotions.

    Runs in a thread to avoid blocking the event loop (backtests are CPU-bound).
    """
    from app.strategy_research.engine import StrategyResearchEngine

    settings = get_settings()
    symbol = settings.symbols[0] if settings.symbols else "BTC_USDT"

    def _generation() -> dict:
        db = SessionLocal()
        try:
            return StrategyResearchEngine(db).run_experiments(symbol, settings.market_data_interval)
        finally:
            db.close()

    summary = await asyncio.to_thread(_generation)
    if summary.get("evaluated"):
        notifier = TelegramNotifier()
        if summary.get("promoted"):
            await notifier.send(
                f"🧪 Strateji Araştırma: {summary['promoted']} strateji production'a terfi etti "
                f"(en iyi fitness={summary.get('best_fitness')}, sharpe={summary.get('best_sharpe')})"
            )
        elif summary.get("best_fitness", 0) > 0:
            await notifier.send(
                f"🧪 Strateji Araştırma turu tamamlandı: {summary['evaluated']} strateji denendi, "
                f"en iyi fitness={summary.get('best_fitness')}"
            )


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
    scheduler.add_job(run_research_loop, "interval", hours=6, max_instances=1)
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
