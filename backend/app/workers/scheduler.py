import asyncio
import signal

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
from app.workers.heartbeat import record_heartbeat
from app.workers.preflight import (
    config_preflight,
    exchange_preflight,
    format_issues,
    has_blocking_errors,
)


async def monitor_portfolio_risk() -> None:
    """Periodic portfolio-level risk limit check with Telegram alerts."""
    from app.models.entities import Portfolio, PaperPosition
    from app.portfolio.engine import PortfolioEngine
    from app.portfolio.risk_model import PortfolioRiskModel

    db = SessionLocal()
    try:
        portfolio = db.query(Portfolio).filter(Portfolio.name == "default").first()
        if not portfolio:
            db.close()
            return

        # Sync paper positions before checking risk
        paper_positions = db.query(PaperPosition).filter(PaperPosition.is_open.is_(True)).all()
        if paper_positions:
            engine = PortfolioEngine(db, portfolio)
            active_pos = [
                {
                    "symbol": p.symbol,
                    "quantity": float(p.quantity),
                    "entry_price": float(p.average_entry_price),
                    "last_price": float(p.last_price),
                }
                for p in paper_positions
            ]
            engine.update_positions(active_pos)

        passed, reason = PortfolioRiskModel(db).check_risk_limits(portfolio)
        if not passed:
            from app.services.notifications.telegram import TelegramNotifier
            await TelegramNotifier().send_portfolio_risk_limit(
                portfolio=portfolio.name,
                reason=reason,
                equity=float(portfolio.total_equity),
            )
            db.add(
                SystemLog(
                    level=LogLevel.warning,
                    source="portfolio_risk",
                    message=f"Portfolio risk limit breached: {reason}",
                )
            )
            db.commit()
    except Exception as exc:
        db.rollback()
        import logging
        logging.getLogger(__name__).error(f"Portfolio risk check failed: {exc}")
    finally:
        db.close()


async def _quote_depegged(client: GateIOClient, settings) -> bool:
    """Best-effort depeg check on the configured reference stablecoin pair."""
    from app.services.risk.stablecoin import is_depegged

    try:
        price = await client.last_price(settings.quote_depeg_reference_pair)
    except Exception as exc:
        # If the depeg check itself fails (network/API error), assume depegged
        # and HALT trading. For a capital preservation bot, this is safer than
        # continuing with potentially corrupted data.
        db = SessionLocal()
        try:
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
        finally:
            db.close()
        return True
    return is_depegged(price, settings.quote_depeg_threshold_pct)


async def monitor_positions() -> None:
    """Fast position-management loop, separate from the 15-min entry cycle.

    Checks stop-loss/take-profit/trailing/breakeven/liquidation on every open
    position at position_monitor_interval_seconds (default 60s) cadence, so a
    fast adverse move is caught before the next entry scan. The exchange-side
    stop (A1) protects even between polls; this tightens the local monitoring
    layer and drives trailing/breakeven amendments faster. Idempotent — safe to
    run alongside run_cycle (which no longer calls manage_open_positions).
    """
    db = SessionLocal()
    client = GateIOClient()
    try:
        engine = TradingEngine(db, client)
        await engine.manage_open_positions()
        # Best-effort heartbeat so the watchdog sees the monitor as alive too.
        try:
            record_heartbeat(db, "position_monitor")
        except Exception:
            pass
    except Exception as exc:
        import logging

        logging.getLogger(__name__).error("monitor_positions failed: %s", exc)
    finally:
        await client.close()
        db.close()


async def run_cycle() -> None:
    settings = get_settings()
    db = SessionLocal()
    client = GateIOClient()
    cycle_status = "ok"
    cycle_detail: str | None = None
    try:
        # 1. Always reconcile open orders with the exchange first.
        await ReconciliationEngine(db, client).reconcile_open_orders()

        # 2. Mark the account to market and derive real equity.
        account = AccountManager(db, client)
        snapshot = await account.refresh()
        equity = snapshot.total_equity

        # 3. Position management now runs on its OWN faster cadence
        # (monitor_positions, every position_monitor_interval_seconds) so a
        # fast adverse move is caught before the next 15-min entry scan. The
        # exchange-side stop (A1) protects even between polls; this tightens
        # the local monitoring layer. We no longer call manage_open_positions
        # here to avoid double work and rate-limit waste.
        engine = TradingEngine(db, client)

        # 4. Global kill-switch: trip on breached limits and halt NEW ENTRIES if
        # tripped (open positions are managed by the monitor_positions job).
        breaker = CircuitBreaker(db)
        drawdown = account.drawdown_pct()
        if breaker.check_and_trip(equity, drawdown):
            return

        # New entries require BOTH the env master switch (BOT_ENABLED) and the
        # strategy's own enable flag. If either is off, no new trades are opened
        # (open positions are still managed above).
        strategy_settings = StrategySettingsRepository(db).current()
        if not settings.bot_enabled or not strategy_settings.is_enabled:
            return

        # Block new entries on a misconfigured live bot (e.g. missing API keys),
        # while still managing open positions above. Cheap, pure config check;
        # the operator gets a one-off Telegram alert at startup.
        preflight_errors = [i for i in config_preflight(settings) if i.level == "error"]
        if preflight_errors:
            db.add(
                SystemLog(
                    level=LogLevel.error,
                    source="preflight",
                    message="New entries blocked by preflight: "
                    + "; ".join(i.message for i in preflight_errors),
                )
            )
            db.commit()
            return

        # Go-live gate: block new entries unless the live strategy passed a recent
        # walk-forward validation on the live timeframe (open positions are still
        # managed above). Stops an un-validated strategy from trading real money.
        if settings.live_require_walkforward:
            from app.services.strategy.validation import live_strategy_validated

            validation = live_strategy_validated(
                db,
                settings.live_strategy,
                settings.market_data_interval,
                settings.live_validation_max_age_days,
            )
            if not validation.ok:
                db.add(
                    SystemLog(
                        level=LogLevel.warning,
                        source="strategy_validation",
                        message=f"New entries blocked: live strategy not validated — {validation.reason}",
                    )
                )
                db.commit()
                return

        # Only size NEW entries against trustworthy equity. Never size against a
        # fallback snapshot (guessed/placeholder equity) regardless of whether
        # keys are configured, nor against a stale snapshot.
        if snapshot.source == "fallback" or account.is_equity_stale():
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
    except Exception as exc:
        # Never leave uncommitted/partial state behind for the next cycle.
        db.rollback()
        cycle_status = "error"
        cycle_detail = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        # Heartbeat: record that the trading loop executed so the API-side
        # watchdog can detect a dead/stuck worker. Best-effort — it must never
        # mask the original error or break the cycle.
        try:
            record_heartbeat(db, "scheduler", cycle_status, cycle_detail)
        except Exception:
            db.rollback()
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


def _on_job_error(event) -> None:
    """APScheduler error listener: surface a failing job immediately (the
    heartbeat staleness alert would otherwise only fire after several cycles)."""
    import logging

    logging.getLogger(__name__).error("scheduler job %s failed: %s", event.job_id, event.exception)
    # send_sync: the listener runs in a synchronous APScheduler context.
    TelegramNotifier().send_sync(
        f"⚠️ Canlı worker job hatası ({event.job_id}): {event.exception}"
    )


async def _run_startup_preflight() -> None:
    """Run live preflight checks once at boot, log them, and alert. Blocking
    errors are reported prominently; new entries are also gated per-cycle in
    run_cycle, so this is the operator-facing summary."""
    settings = get_settings()
    issues = list(config_preflight(settings))
    client = GateIOClient()
    try:
        issues += await exchange_preflight(settings, client)
    except Exception as exc:  # noqa: BLE001 - preflight must never crash the worker
        import logging

        logging.getLogger(__name__).warning("exchange preflight failed: %s", exc)
    finally:
        await client.close()

    db = SessionLocal()
    try:
        # Go-live gate status (needs DB): surface why live may be blocked.
        if settings.live_require_walkforward:
            from app.services.strategy.validation import live_strategy_validated
            from app.workers.preflight import PreflightIssue

            validation = live_strategy_validated(
                db,
                settings.live_strategy,
                settings.market_data_interval,
                settings.live_validation_max_age_days,
            )
            if not validation.ok:
                issues.append(PreflightIssue(
                    "warning", "strategy_not_validated",
                    f"Canlı strateji doğrulanmadı — yeni girişler engellendi: {validation.reason}. "
                    f"Canlı timeframe'de ({settings.market_data_interval}) geçer bir walk-forward çalıştırın.",
                ))
        for issue in issues:
            level = LogLevel.error if issue.level == "error" else LogLevel.warning
            db.add(SystemLog(level=level, source="preflight", message=issue.message))
        db.commit()
    finally:
        db.close()

    if not settings.bot_enabled:
        return
    if has_blocking_errors(issues):
        await TelegramNotifier().send(
            "🔴 Canlı PREFLIGHT BAŞARISIZ — yeni girişler engellendi:\n"
            + format_issues(issues)
        )
    elif issues:
        await TelegramNotifier().send("⚠️ Canlı preflight uyarıları:\n" + format_issues(issues))
    else:
        await TelegramNotifier().send("✅ Canlı preflight: tüm kontroller geçti.")


async def _record_initial_heartbeat() -> None:
    """Prime the heartbeat on boot so the watchdog sees the worker as alive
    immediately, rather than waiting for the first 15-minute cycle."""
    db = SessionLocal()
    try:
        record_heartbeat(db, "scheduler", "starting", None)
    except Exception:
        db.rollback()
    finally:
        db.close()


async def main() -> None:
    configure_logging()
    settings = get_settings()
    # Ensure the schema exists before reconciliation/queries run. On Railway each
    # service boots independently, so the scheduler can start before the API has
    # migrated a fresh DB. init_db is idempotent (alembic upgrade head); a failure
    # is logged but non-fatal (the API will also migrate, and per-cycle work has
    # its own error handling).
    try:
        from app.db.init_db import init_db

        init_db()
    except Exception:
        import logging

        logging.getLogger(__name__).warning("scheduler: init_db failed at startup", exc_info=True)
    await startup_recovery()
    await _record_initial_heartbeat()
    await TelegramNotifier().send(
        f"🟢 Canlı worker başlatıldı (market={settings.trading_market}, "
        f"strategy={settings.live_strategy}, bot_enabled={settings.bot_enabled})."
    )
    await _run_startup_preflight()

    # Stream live prices into the shared cache in the background.
    ws_client = GateIOWebSocketClient(settings.symbols)
    ws_task = asyncio.create_task(ws_client.run())

    from apscheduler.events import EVENT_JOB_ERROR

    scheduler = AsyncIOScheduler()
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    # Position management runs on a FASTER cadence than entries so a fast
    # adverse move is caught before the next 15-min scan. The exchange-side
    # stop (A1) protects even between polls; this tightens the local layer.
    pos_interval = max(int(get_settings().position_monitor_interval_seconds), 15)
    scheduler.add_job(monitor_positions, "interval", seconds=pos_interval, max_instances=1)
    # Entry scan + candle ingestion cadence tracks the trading timeframe so a
    # faster strategy (e.g. 5m momentum) is not lagged a full bar by a fixed 15m
    # scan. Bounded below at 1 minute to respect rate limits.
    entry_interval = max(int(get_settings().live_entry_interval_minutes), 1)
    scheduler.add_job(run_cycle, "interval", minutes=entry_interval, max_instances=1)
    scheduler.add_job(ingest_market_data, "interval", minutes=entry_interval, max_instances=1)
    scheduler.add_job(monitor_portfolio_risk, "interval", minutes=15, max_instances=1)
    scheduler.add_job(run_research_loop, "interval", hours=6, max_instances=1)
    scheduler.add_job(run_learning_cycle, "cron", hour=3, minute=0, max_instances=1)
    scheduler.add_job(weekly_learning_report, "cron", day_of_week="mon", hour=8, minute=0)
    scheduler.add_job(daily_report, "cron", hour=21, minute=0)
    scheduler.start()
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    try:
        await stop_event.wait()
    finally:
        # Graceful-shutdown alert: an unexpected restart then shows up as a
        # stop followed by a start (or, on a hard crash, the watchdog fires).
        await TelegramNotifier().send("🟠 Canlı worker durduruluyor.")
        scheduler.shutdown(wait=False)
        ws_client.stop()
        ws_task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
