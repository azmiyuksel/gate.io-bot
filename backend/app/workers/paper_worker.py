import asyncio
import logging
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
    retry_delay = 1
    while True:
        db = SessionLocal()
        try:
            account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
            if account is None:
                account = PaperAccount()
                db.add(account)
                db.commit()
                db.refresh(account)
            try:
                if account.cash_balance <= 0:
                    logger.warning("Paper account cash_balance was %s, resetting to initial_balance", account.cash_balance)
                    account.cash_balance = account.initial_balance
                    account.realized_pnl = 0
                    db.commit()
            except (TypeError, AttributeError):
                pass

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
            # ordinary leveraged volatility (5%/25% spot limits). Raise legacy values
            # to the configured futures limits. Only bumps UP from the known spot
            # defaults, so it never tightens a deliberately-set value.
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

            logger.info("Paper worker starting: account=%s cash=%s status=%s", account.id, account.cash_balance, account.status)
            strategy = CapitalPreservationAdapter()
            engine = PaperTradingEngine(db, account, strategy=strategy)
            # Only start if the account status is RUNNING (not stopped by user)
            if account.status == PaperBotStatus.running:
                await engine.start(settings.symbols)
            else:
                logger.info("Paper worker: account not running (status=%s), waiting for start signal", account.status)
                refresh_failures = 0
                while account.status != PaperBotStatus.running:
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
                            account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
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
