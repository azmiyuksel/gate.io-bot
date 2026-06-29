import asyncio
import contextlib
import logging
import signal
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.entities import PaperAccount, PaperLog
from app.models.enums import PaperBotStatus
from app.paper_trading.engine import PaperTradingEngine
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.strategy_adapter import CapitalPreservationAdapter

logger = logging.getLogger(__name__)

MAX_RETRY_DELAY = 60  # seconds
LOG_RETENTION_DAYS = 7
# High-volume per-evaluation diagnostics (entry_skipped / risk_check) are logged
# for every symbol every cycle. The dashboard only reads a 24h window, so prune
# them aggressively (48h = window + buffer) to keep the table — and the signal
# diagnostics query — small. Lower-volume events keep the 7-day retention above.
DIAG_RETENTION_HOURS = 48
DIAG_EVENTS = ("entry_skipped", "risk_check")


async def main() -> None:
    configure_logging()
    settings = get_settings()
    # Multi-account: the worker drives whichever PaperAccount row matches
    # `paper_account_name` in settings. Lets a second worker instance (e.g. a
    # different live mirror config) trade its own paper account without code
    # changes — and keeps /api/v1/* endpoints that default to "default".
    account_name = getattr(settings, "paper_account_name", "default")
    # Graceful shutdown: Railway sends SIGTERM on redeploy/stop. Without handling
    # it, the engine is killed mid-trade (DB session, WS, half-applied state).
    # The stop event lets the worker break out of engine.start() and the waiting
    # loop cleanly so it can flush the DB and close the WS before exiting.
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # add_signal_handler is unavailable on some platforms (e.g. Windows
            # ProactorEventLoop). Fall back to KeyboardInterrupt handling below.
            pass
    # NOTE: the worker does NOT call init_db() at boot. On Railway the API service
    # is the authoritative migrator (it has a healthcheck and boots reliably), and
    # the worker's own init_db() was hanging the worker indefinitely — alembic
    # opens its OWN database connection (outside the SQLAlchemy pool, so
    # pool_timeout doesn't apply) and blocks forever when the Postgres connection
    # limit is saturated by the API's pool. The worker's existing retry loop
    # (OperationalError below) handles a not-yet-migrated DB: it retries until the
    # API finishes migrating, then proceeds. A best-effort init_db added latency
    # and a deadlock risk with no upside once the API is the sole migrator.
    retry_delay = 1
    while True:
        db = SessionLocal()
        try:
            account = db.query(PaperAccount).filter(PaperAccount.name == account_name).first()
            if account is None:
                account = PaperAccount()
                db.add(account)
                db.commit()
                db.refresh(account)

            # Autostart: a fresh PaperAccount defaults to STOPPED, so a Railway
            # deploy sits idle until someone clicks Start in the dashboard. When
            # paper_autostart_on_boot is true, flip STOPPED -> RUNNING on boot so
            # paper begins trading immediately. A PAUSED account (auto-paused by a
            # risk limit) is also resumed IF the risk limits are now clear — a
            # redeploy with relaxed thresholds should not leave the book stuck
            # PAUSED under the old, tighter limits. The limits are checked via the
            # risk simulator so the resume is safe (never overrides an active breach).
            if getattr(settings, "paper_autostart_on_boot", True):
                if account.status == PaperBotStatus.stopped:
                    account.status = PaperBotStatus.running
                    db.commit()
                    logger.info(
                        "Paper worker: autostart_on_boot — account flipped STOPPED -> RUNNING"
                    )
                elif account.status == PaperBotStatus.paused:
                    try:
                        from app.paper_trading.risk_simulator import PaperRiskSimulator

                        risk = PaperRiskSimulator(db, account)
                        dd = risk._check_drawdown()
                        daily_loss = risk._daily_loss_pct()
                        # Use the effective (mirrored/env) limits, not the stale DB column.
                        from app.paper_trading.mirror import resolve_paper_exec

                        exec_ = resolve_paper_exec(db, settings)
                        max_dd = exec_.max_drawdown_pct
                        max_dl = exec_.daily_max_loss_pct
                        if abs(dd) < max_dd and daily_loss < max_dl:
                            account.status = PaperBotStatus.running
                            db.commit()
                            logger.info(
                                "Paper worker: autostart_on_boot — account resumed PAUSED -> RUNNING "
                                "(dd=%.4f < %.4f, daily_loss=%.4f < %.4f)",
                                float(dd), float(max_dd), float(daily_loss), float(max_dl),
                            )
                        else:
                            logger.info(
                                "Paper worker: account PAUSED, limits still breached "
                                "(dd=%.4f vs %.4f, daily_loss=%.4f vs %.4f) — waiting for auto-resume",
                                float(dd), float(max_dd), float(daily_loss), float(max_dl),
                            )
                    except Exception:
                        logger.warning("Paper worker: autostart resume-from-pause check failed", exc_info=True)
            # NOTE: a previous version silently reset a wiped-out account
            # (cash_balance <= 0) back to initial_balance on every boot. That
            # destroys accounting history and hides a blow-up from the user.
            # Instead, preserve the realized PnL and let the user decide whether
            # to reset via the dashboard's "Sıfırla" (reset) action. We only
            # log the degraded state so it is visible without rewriting history.
            if account.cash_balance <= 0:
                logger.warning(
                    "Paper account cash_balance is non-positive (%s); preserving history "
                    "(reset manually from the dashboard if desired)",
                    account.cash_balance,
                )

            # Mirror live: when paper mirrors the live account, write the live
            # (mirrored) limits onto the account so the dashboard shows the same
            # limits the gate enforces. Otherwise apply the legacy futures migration.
            if settings.paper_mirror_live:
                try:
                    from app.paper_trading.mirror import resolve_paper_exec
                    ex = resolve_paper_exec(db, settings)
                    account.max_exposure_pct = ex.max_exposure_pct
                    account.max_daily_loss_pct = ex.daily_max_loss_pct
                    account.max_drawdown_pct = ex.max_drawdown_pct
                    account.max_open_positions = ex.max_open_positions
                    db.commit()
                except Exception:
                    db.rollback()

            # Futures migration: an account created with the legacy spot risk limits
            # would block leveraged trading (exposure cap <1x) or auto-pause on
            # ordinary leveraged volatility (5%/25% spot limits). Previously this
            # ran on EVERY boot to raise legacy values up to the configured
            # futures limits; new accounts now ship with futures defaults and any
            # deployed account has long since been migrated, so the per-boot
            # update became (a) dead work and (b) a per-boot DB write that overrode
            # operator-tuned env values. Default OFF; flip the flag to migrate a
            # long-stale account that predates the change.
            if getattr(settings, "paper_legacy_futures_migration_enabled", False):
                try:
                    from decimal import Decimal as _D
                    changed = False
                    if not settings.paper_mirror_live and account.max_exposure_pct is not None and _D(str(account.max_exposure_pct)) < _D("1"):
                        account.max_exposure_pct = _D(str(settings.paper_leverage))
                        changed = True
                    if not settings.paper_mirror_live and account.max_daily_loss_pct is not None and _D(str(account.max_daily_loss_pct)) <= _D("0.05"):
                        account.max_daily_loss_pct = _D(str(settings.paper_max_daily_loss_pct))
                        changed = True
                    if not settings.paper_mirror_live and account.max_drawdown_pct is not None and _D(str(account.max_drawdown_pct)) <= _D("0.25"):
                        account.max_drawdown_pct = _D(str(settings.paper_max_drawdown_pct))
                        changed = True
                    if changed:
                        logger.info(
                            "Paper account risk limits migrated to futures: exposure=%s daily_loss=%s drawdown=%s",
                            account.max_exposure_pct, account.max_daily_loss_pct, account.max_drawdown_pct,
                        )
                        db.commit()
                except Exception:
                    # Best-effort migration: never let a bad/mocked value abort startup.
                    pass
            portfolio = PaperPortfolio(db, account)
            portfolio.record_equity()
            db.commit()

            # Clean up old log entries
            try:
                now = datetime.now(UTC)
                cutoff = now - timedelta(days=LOG_RETENTION_DAYS)
                deleted = (
                    db.query(PaperLog)
                    .filter(PaperLog.account_id == account.id, PaperLog.created_at < cutoff)
                    .delete(synchronize_session=False)
                )
                # Aggressively prune the high-volume diagnostic events on a much
                # shorter horizon so the signal-diagnostics table stays bounded.
                diag_cutoff = now - timedelta(hours=DIAG_RETENTION_HOURS)
                deleted += (
                    db.query(PaperLog)
                    .filter(
                        PaperLog.account_id == account.id,
                        PaperLog.event.in_(DIAG_EVENTS),
                        PaperLog.created_at < diag_cutoff,
                    )
                    .delete(synchronize_session=False)
                )
                if deleted:
                    db.commit()
                    logger.info("Paper worker: cleaned %s old log entries", deleted)
            except Exception:
                db.rollback()
                logger.warning("Paper worker: log cleanup failed", exc_info=True)

            # NOTE: a previous version of this worker rewrote the LIVE
            # StrategySettings (max_open_positions, atr_multiplier, ...) on every
            # boot "for profitability". That is a separation-of-concerns
            # violation: the paper worker must never mutate live-trading
            # parameters, especially in a paper-only deployment where the live
            # engine may share the same DB. Paper reads live settings (via
            # resolve_paper_exec) but must not write them.

            logger.info("Paper worker starting: account=%s cash=%s status=%s", account.id, account.cash_balance, account.status)
            strategy = CapitalPreservationAdapter()
            engine = PaperTradingEngine(db, account, strategy=strategy)
            # Only start if the account status is RUNNING (not stopped by user)
            if account.status == PaperBotStatus.running:
                stop_event.clear()
                retry_delay = 1
                max_retry_delay = 60
                while True:
                    engine_task = asyncio.create_task(engine.start(settings.symbols))
                    shutdown_task = asyncio.create_task(stop_event.wait())
                    try:
                        await asyncio.wait(
                            {engine_task, shutdown_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    finally:
                        if not engine_task.done():
                            # Do NOT stamp status=stopped onto the account: this
                            # is a worker shutdown (redeploy/SIGTERM), not a user
                            # stop. A new container is already starting and has
                            # set status=RUNNING; writing STOPPED here wins the
                            # race and leaves the bot idle after every deploy.
                            engine.stop(set_status=False)
                            with contextlib.suppress(asyncio.CancelledError):
                                await engine_task
                        shutdown_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await shutdown_task

                    # If shutdown was requested, exit immediately regardless of
                    # whether the engine succeeded or failed.
                    if stop_event.is_set():
                        logger.info("Paper worker: shutdown signal received")
                        break

                    # If the engine task raised an exception, retry with backoff.
                    # A normal return means the engine exited cleanly (e.g. the
                    # account was stopped via the API).
                    if engine_task.exception() is not None:
                        logger.warning(
                            "Paper worker: engine error, retrying in %ds: %s",
                            retry_delay,
                            engine_task.exception(),
                        )
                        db.close()
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, max_retry_delay)
                        db = SessionLocal()
                        account = db.query(PaperAccount).filter(PaperAccount.name == account_name).first()
                        if account is None:
                            logger.info("Paper worker: account disappeared after retry, exiting")
                            break
                        engine = PaperTradingEngine(db, account, strategy=strategy)
                        continue

                    # Engine exited normally — stop the worker.
                    break

                logger.info("Paper worker: engine exited, shutting down")
                break
            else:
                logger.info("Paper worker: account not running (status=%s), waiting for start signal", account.status)
                refresh_failures = 0
                while account.status != PaperBotStatus.running:
                    # Also exit when a shutdown signal arrives so a redeploy
                    # does not leave this worker stuck in the wait loop.
                    if stop_event.is_set():
                        logger.info("Paper worker: shutdown signal received while waiting for start")
                        db.close()
                        return
                    await asyncio.sleep(5)
                    try:
                        db.refresh(account)
                        refresh_failures = 0
                    except Exception:
                        refresh_failures += 1
                        if refresh_failures >= 3:
                            logger.warning("Paper worker: DB refresh failed %s times, recreating session", refresh_failures)
                            try:
                                db.close()
                            except Exception:
                                pass
                            db = SessionLocal()
                            account = db.query(PaperAccount).filter(PaperAccount.name == account_name).first()
                            if account is None:
                                account = PaperAccount()
                                db.add(account)
                                db.commit()
                                db.refresh(account)
                            refresh_failures = 0
                db.close()
                continue
            break
        except (OperationalError, OSError) as exc:
            logger.warning("Paper worker connection error (retry in %ss): %s", retry_delay, exc)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        except Exception as exc:
            logger.error("Paper worker fatal error, restarting: %s", exc)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
        finally:
            try:
                db.close()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
