from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.entities import PaperAccount, PaperEquityCurve, PaperLog
from app.models.enums import LogLevel, PaperBotStatus
from app.paper_trading.models import MarketData, TradingSignal
from app.paper_trading.portfolio import PaperPortfolio

_ROLLING_24H = timedelta(hours=24)


class PaperRiskSimulator:
    def __init__(self, db: Session, account: PaperAccount) -> None:
        self.db = db
        self.account = account
        self.portfolio = PaperPortfolio(db, account)

    def approve_signal(self, signal: TradingSignal, data: MarketData) -> tuple[bool, str]:
        from app.core.config import get_settings
        from app.paper_trading.mirror import resolve_paper_exec

        if self.account.status != PaperBotStatus.running:
            return False, "system_not_running"
        equity = self.portfolio.equity()
        if equity <= 0:
            return False, "no_equity"

        # Circuit breaker: mirror the live engine's consecutive-loss circuit
        # breaker so paper pauses when its own track record shows a losing
        # streak. Paper uses a higher threshold (paper_circuit_breaker_losses,
        # default 10) so a cold-start loss streak doesn't pause the book before
        # it can recover. 0 disables the circuit breaker entirely.
        settings = get_settings()
        cb_threshold = int(getattr(settings, "paper_circuit_breaker_losses", 10))
        if cb_threshold > 0 and self._consecutive_losses() >= cb_threshold:
            self.pause("circuit_breaker_consecutive_losses")
            return False, "circuit_breaker"

        # Mirror live: enforce the live account's limits (max-positions/exposure/
        # drawdown/daily-loss) so paper pauses under the same conditions the live
        # circuit breaker would. Otherwise use the account's own columns.
        exec_ = resolve_paper_exec(self.db, get_settings())
        max_positions = exec_.max_open_positions if exec_.mirror else self.account.max_open_positions
        max_exposure = exec_.max_exposure_pct if exec_.mirror else self.account.max_exposure_pct
        max_drawdown = exec_.max_drawdown_pct if exec_.mirror else self.account.max_drawdown_pct
        max_daily_loss = exec_.daily_max_loss_pct if exec_.mirror else self.account.max_daily_loss_pct

        open_positions = self.portfolio.open_positions()
        if len(open_positions) >= max_positions:
            return False, "max_open_positions"
        if any(p.symbol == signal.symbol for p in open_positions):
            return False, "already_in_position"
        if self.portfolio.exposure_pct() >= max_exposure:
            return False, "max_exposure"
        latest_dd = self._check_drawdown()
        if abs(latest_dd) >= max_drawdown:
            self.pause("max_drawdown_reached")
            return False, "max_drawdown_reached"
        if self._daily_loss_pct() >= max_daily_loss:
            self.pause("daily_loss_limit_reached")
            return False, "daily_loss_limit_reached"
        return True, "approved"

    def pause(self, reason: str) -> None:
        self.account.status = PaperBotStatus.paused
        self.db.add(PaperLog(
            account_id=self.account.id,
            level=LogLevel.warning,
            event="system_paused",
            message=reason,
            payload={"reason": reason, "paused_at": datetime.now(UTC).isoformat()},
        ))
        self.db.commit()

    def maybe_auto_resume(self) -> bool:
        if self.account.status != PaperBotStatus.paused:
            return False
        last_pause = (
            self.db.query(PaperLog)
            .filter(
                PaperLog.account_id == self.account.id,
                PaperLog.event == "system_paused",
            )
            .order_by(desc(PaperLog.created_at))
            .first()
        )
        if last_pause is None:
            return False
        paused_at = last_pause.created_at
        pause_reason = last_pause.message
        # Configurable cooldowns: paper uses shorter cooldowns than live so the
        # simulation resumes quickly and keeps producing data.
        from app.core.config import get_settings

        settings = get_settings()
        if "max_drawdown" in (pause_reason or ""):
            cooldown_hours = float(getattr(settings, "paper_auto_resume_drawdown_cooldown_hours", 1.0))
        else:
            cooldown_hours = float(getattr(settings, "paper_auto_resume_daily_loss_cooldown_hours", 0.5))
        if datetime.now(UTC) - paused_at < timedelta(hours=cooldown_hours):
            return False
        equity = self.portfolio.equity()
        if equity <= 0:
            return False
        dd = self._check_drawdown()
        if dd >= self.account.max_drawdown_pct:
            return False
        loss = self._daily_loss_pct()
        if loss >= self.account.max_daily_loss_pct:
            return False
        self.account.status = PaperBotStatus.running
        self._log_info("system_auto_resumed", "Auto-resumed after cooldown")
        return True

    def _log_info(self, event: str, message: str) -> None:
        self.db.add(PaperLog(account_id=self.account.id, level=LogLevel.info, event=event, message=message))
        self.db.commit()

    def _check_drawdown(self) -> Decimal:
        point = (
            self.db.query(PaperEquityCurve)
            .filter(PaperEquityCurve.account_id == self.account.id)
            .order_by(desc(PaperEquityCurve.timestamp))
            .first()
        )
        if point is None:
            return Decimal("0")
        return abs(point.drawdown)

    def _daily_loss_pct(self) -> Decimal:
        """Compute 24h rolling loss using DB equity curve records."""
        equity = self.portfolio.equity()
        now = datetime.now(UTC)
        cutoff = now - _ROLLING_24H

        peak_24h = (
            self.db.query(func.max(PaperEquityCurve.equity))
            .filter(
                PaperEquityCurve.account_id == self.account.id,
                PaperEquityCurve.timestamp >= cutoff,
            )
            .scalar()
        )
        if peak_24h is None:
            peak_24h = self.account.initial_balance

        peak = Decimal(str(peak_24h))
        if peak <= 0:
            return Decimal("0")

        # Also consider current equity (not yet recorded in DB)
        peak = max(peak, equity)
        loss = max(peak - equity, Decimal("0"))
        return loss / peak

    def _consecutive_losses(self) -> int:
        """Count consecutive losing trades from the most recent closed positions.

        Returns up to ``paper_circuit_breaker_losses`` recent closed positions so
        the count is accurate for the configured threshold (was hardcoded to 5,
        which capped the count at 5 even when the threshold was raised to 10).
        """
        from app.models.entities import PaperPosition

        from app.core.config import get_settings

        limit = int(getattr(get_settings(), "paper_circuit_breaker_losses", 10))
        # Floor at 5 so a disabled breaker (0) still returns a meaningful count
        # for diagnostics (the caller checks >0 before using it).
        limit = max(limit, 5)
        recent = (
            self.db.query(PaperPosition)
            .filter(
                PaperPosition.account_id == self.account.id,
                PaperPosition.is_open.is_(False),
                PaperPosition.realized_pnl.isnot(None),
            )
            .order_by(PaperPosition.closed_at.desc())
            .limit(limit)
            .all()
        )
        count = 0
        for pos in recent:
            if pos.realized_pnl is not None and Decimal(str(pos.realized_pnl)) < 0:
                count += 1
            else:
                break
        return count
