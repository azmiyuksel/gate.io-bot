"""API-side watchdog that alerts when the live trading worker goes silent.

Runs as a background task inside the FastAPI process (a different process from
the scheduler worker), so it can detect the worker dying, hanging, or being
killed — none of which an in-process check could catch. Alerts are sent once on
each healthy<->stale transition (not every poll) to avoid spam.
"""
from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.entities import SystemLog
from app.models.enums import LogLevel
from app.services.notifications.telegram import TelegramNotifier
from app.workers.heartbeat import DEFAULT_WORKER, heartbeat_age_seconds, is_stale

logger = logging.getLogger(__name__)


def _format_age(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "hiç (heartbeat yok)"
    minutes = age_seconds / 60
    return f"{minutes:.1f} dk önce"


def next_alert_event(
    age_seconds: float | None, stale_threshold_seconds: float, was_stale: bool | None
) -> tuple[bool, str | None]:
    """Decide the next watchdog state and which alert (if any) to emit.

    ``was_stale`` is None on the very first observation so we prime the baseline
    silently (no boot-time false alarm). Returns ``(is_stale_now, event)`` where
    ``event`` is "down", "recovered", or None.
    """
    stale_now = is_stale(age_seconds, stale_threshold_seconds)
    if was_stale is None:
        return stale_now, None
    if stale_now and not was_stale:
        return True, "down"
    if not stale_now and was_stale:
        return False, "recovered"
    return stale_now, None


def _log(db, level: LogLevel, message: str) -> None:
    try:
        db.add(SystemLog(level=level, source="worker_watchdog", message=message))
        db.commit()
    except Exception:
        db.rollback()


async def worker_watchdog_loop(worker: str = DEFAULT_WORKER) -> None:
    """Background loop: poll the worker heartbeat and alert on transitions."""
    settings = get_settings()
    if not settings.worker_watchdog_enabled:
        return
    log = get_logger("app.watchdog")
    notifier = TelegramNotifier()
    threshold = float(settings.worker_heartbeat_stale_seconds)
    interval = max(int(settings.worker_watchdog_check_seconds), 30)
    was_stale: bool | None = None

    log.info("watchdog_started", extra={"worker": worker, "threshold_s": threshold})
    while True:
        try:
            await asyncio.sleep(interval)
            db = SessionLocal()
            try:
                age = heartbeat_age_seconds(db, worker)
                stale_now, event = next_alert_event(age, threshold, was_stale)
                if event == "down":
                    msg = (
                        f"🔴 UYARI: Canlı işlem worker'ı ({worker}) yanıt vermiyor — "
                        f"son heartbeat {_format_age(age)}. Açık pozisyonlar yönetilmiyor "
                        f"olabilir; worker'ı kontrol edin."
                    )
                    _log(db, LogLevel.error, msg)
                    await notifier.send(msg)
                elif event == "recovered":
                    msg = f"✅ Canlı işlem worker'ı ({worker}) yeniden çalışıyor (heartbeat alındı)."
                    _log(db, LogLevel.info, msg)
                    await notifier.send(msg)
                was_stale = stale_now
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("watchdog_iteration_failed")
