import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.account.engine import AccountManager
from app.auto_learning.engine import AutoLearningEngine
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.market_data.ingestion import MarketDataIngestion
from app.market_data.websocket import GateIOWebSocketClient
from app.models.entities import SystemLog
from app.models.enums import LogLevel
from app.reconciliation.engine import ReconciliationEngine
from app.repositories.trading import StrategySettingsRepository
from app.services.exchange.gateio import GateIOClient
from app.services.notifications.telegram import TelegramNotifier
from app.services.risk.circuit_breaker import CircuitBreaker
from app.services.trading_engine import TradingEngine


async def _quote_depegged(client: GateIOClient, settings) -> bool:
    """Best-effort depeg check on the configured reference stablecoin pair."""
    from app.services.risk.stablecoin import is_depegged

    try:
        price = await client.last_price(settings.quote_depeg_reference_pair)
    except Exception as exc:
        # If the depeg check itself fails (network/API error), assume depegged
        # and HALT trading. For a capital preservation bot, this is safer than
        # continuing with potentially corrupted data.
        from app.models.entities import SystemLog
        from app.models.enums import LogLevel
        from app.db.session import SessionLocal
        
        db = SessionLocal()
        db.add(
            SystemLog(
                level=LogLevel.error,
                source="stablecoin",
                message=(
                    f"Depeg check failed for {settings.quote_depeg_reference_pair}: {exc}. "
                    f"Assuming depegged and HALTING trading."
                ),
            )
        )
        db.commit()
        db.close()
        return True
    return is_depegged(price, settings.quote_depeg_threshold_pct)


async def run_cycle() -> None:
    settings = get_settings()
    db = SessionLocal()
    client = GateIOClient()
    try:
        # 1. Always reconcile open orders with the exchange first.
        await ReconciliationEngine(db, client).reconcile_open_orders()

        # 2. Mark the account to market and derive real equity.
        account = AccountManager(db, client)
        snapshot = await account.refresh()
        equity = snapshot.total_equity

        # 3. Global kill-switch: trip on breached limits, halt cycle if tripped.
        breaker = CircuitBreaker(db)
        drawdown = account.drawdown_pct()
        if breaker.check_and_trip(equity, drawdown):
            return

        engine = TradingEngine(db, client)
        # Always manage open positions so stops/take-profits are honoured, even
        # while new entries are paused.
        await engine.manage_open_positions()

        # New entries require BOTH the env master switch (BOT_ENABLED) and the
        # strategy's own enable flag. If either is off, no new trades are opened
        # (open positions are still managed above).
        strategy_settings = StrategySettingsRepository(db).current()
        if not settings.bot_enabled or not strategy_settings.is_enabled:
            return

        # Only size NEW entries against trustworthy equity. If the exchange was
        # unreachable (fallback snapshot) while API keys are configured, or the
        # equity is stale, skip new entries rather than risk-sizing on guesses.
        has_keys = bool(settings.gateio_api_key and settings.gateio_api_secret)
        if (snapshot.source == "fallback" and has_keys) or account.is_equity_stale():
            db.add(
                SystemLog(
                    level=LogLevel.warning,
                    source="account",
                    message=(
                        f"New entries skipped: equity not trustworthy "
                        f"(source={snapshot.source}, age={account.snapshot_age_seconds()}s)"
                    ),
                )
            )
            db.commit()
            return

        # Stablecoin depeg guard: the account is denominated in the quote
        # stablecoin, so a depeg is a portfolio-wide risk — pause new entries.
        if settings.quote_depeg_halt and await _quote_depegged(client, settings):
            db.add(
                SystemLog(
                    level=LogLevel.warning,
                    source="stablecoin",
                    message=(
                        f"New entries skipped: {settings.quote_depeg_reference_pair} "
                        f"depeg beyond {settings.quote_depeg_threshold_pct:.2%}"
                    ),
                )
            )
            db.commit()
            await TelegramNotifier().send(
                f"⚠️ Stablecoin depeg uyarısı: {settings.quote_depeg_reference_pair} "
                f"parite sapması eşiği aştı; yeni girişler duraklatıldı."
            )
            return

        for symbol in settings.symbols:
            try:
                await engine.scan_symbol(symbol, equity)
            except Exception as exc:
                db.add(
                    SystemLog(
                        level=LogLevel.error,
                        source="scan_symbol",
                        message=f"{symbol}: scan failed, continuing with other symbols — {exc}",
                    )
                )
                db.commit()
    except Exception:
        # Never leave uncommitted/partial state behind for the next cycle.
        db.rollback()
        raise
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


async def run_learning_cycle() -> None:
    """Continuous auto-learning: evolve + validate candidates, never auto-deploy.

    Runs in a worker thread (CPU-bound) and only ever creates promotion *requests*
    that a human must approve.
    """
    settings = get_settings()
    if not settings.learning_enabled:
        return
    symbol = settings.symbols[0] if settings.symbols else "BTC_USDT"

    def _cycle() -> dict:
        db = SessionLocal()
        try:
            return AutoLearningEngine(db).run_cycle(symbol, settings.market_data_interval)
        finally:
            db.close()

    summary = await asyncio.to_thread(_cycle)
    if summary.get("promotion_requests"):
        await TelegramNotifier().send(
            f"🧠 Auto-Learning: {summary['promotion_requests']} strateji insan onayı bekliyor "
            f"(cycle #{summary.get('cycle_id')}, {summary.get('strategies_validated')} doğrulandı). "
            f"Onay olmadan canlıya geçiş YOK."
        )


async def weekly_learning_report() -> None:
    db = SessionLocal()
    try:
        report = AutoLearningEngine(db).weekly_report(7)
        await TelegramNotifier().send(
            f"📚 Haftalık Öğrenme Raporu: {report.patterns_learned} pattern, "
            f"{report.new_candidates} aday, {report.failed_strategies} elenen, "
            f"{report.promotion_requests} terfi talebi."
        )
    finally:
        db.close()


async def daily_report() -> None:
    # Housekeeping: drop refresh tokens that have already expired.
    from app.api.v1.auth import purge_expired_refresh_tokens

    db = SessionLocal()
    try:
        purge_expired_refresh_tokens(db)
    finally:
        db.close()
    await TelegramNotifier().send("Daily report: check dashboard for PnL, drawdown and open risk.")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    await startup_recovery()

    # Stream live prices into the shared cache in the background.
    ws_client = GateIOWebSocketClient(settings.symbols)
    ws_task = asyncio.create_task(ws_client.run())

    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_cycle, "interval", minutes=15, max_instances=1)
    scheduler.add_job(ingest_market_data, "interval", minutes=15, max_instances=1)
    scheduler.add_job(run_research_loop, "interval", hours=6, max_instances=1)
    scheduler.add_job(run_learning_cycle, "cron", hour=3, minute=0, max_instances=1)
    scheduler.add_job(weekly_learning_report, "cron", day_of_week="mon", hour=8, minute=0)
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
