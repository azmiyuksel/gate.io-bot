from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.trading import (
    AccountSnapshotRepository,
    PositionRepository,
    StrategySettingsRepository,
    TradeRepository,
    day_start_utc,
    week_start_utc,
)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    quantity: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")


def drawdown_risk_multiplier(
    drawdown: Decimal, max_drawdown: Decimal, floor: Decimal = Decimal("0")
) -> Decimal:
    """Graded de-risking: shrink position size as account drawdown deepens.

    Returns 1.0 at no drawdown and falls linearly toward `floor` as drawdown
    approaches `max_drawdown` (where the circuit breaker hard-stops). This
    respects recovery math — deeper drawdowns need disproportionately larger
    gains to recover, so risk is cut before the hard limit."""
    if max_drawdown <= 0:
        raise ValueError("max_drawdown must be positive")
    if drawdown <= 0:
        return Decimal("1")
    mult = Decimal("1") - (drawdown / max_drawdown)
    return max(floor, min(mult, Decimal("1")))


def vol_target_multiplier(
    atr_pct: Decimal, target_pct: Decimal, min_mult: Decimal, max_mult: Decimal
) -> Decimal:
    """Volatility-targeting size multiplier: scale inversely to volatility so
    per-trade risk is steadier across calm/volatile markets.

    atr_pct is ATR as a fraction of price; when it exceeds the target, size is
    reduced; when below, size is increased (within [min_mult, max_mult])."""
    if atr_pct <= 0:
        return Decimal("1")
    raw = target_pct / atr_pct
    return max(min_mult, min(raw, max_mult))


class RiskManager:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.positions = PositionRepository(db)
        self.trades = TradeRepository(db)
        self.settings = StrategySettingsRepository(db)
        self.snapshots = AccountSnapshotRepository(db)

    def _period_pnl(self, current_equity: Decimal, since) -> Decimal:
        """Mark-to-market PnL for the period: current equity minus equity carried
        into the period (includes UNREALIZED PnL of open positions, since
        `current_equity` is marked to market). Falls back to realized-only PnL
        when no equity snapshots exist. This stops an open position from blowing
        through the loss limit while reporting zero realized loss."""
        start_equity = self.snapshots.equity_at_period_start(since)
        if start_equity is not None and start_equity > 0:
            return current_equity - start_equity
        return self.trades.pnl_since(since)

    def approve_entry(
        self, equity: Decimal, entry: Decimal, atr_value: Decimal, side: str = "long"
    ) -> RiskDecision:
        # Master env kill-switch: live entries require BOT_ENABLED=true as well
        # as the strategy's own enable flag (defense-in-depth alongside scheduler).
        if not get_settings().bot_enabled:
            return RiskDecision(False, "bot_disabled")
        if entry <= 0 or atr_value <= 0:
            return RiskDecision(False, "invalid_price_data")
        # Defense-in-depth: never open a new position while the circuit breaker is
        # tripped, even if some other path failed to halt the strategy.
        from app.services.risk.circuit_breaker import CircuitBreaker

        if CircuitBreaker(self.db).is_tripped():
            return RiskDecision(False, "circuit_breaker_tripped")
        # Lock the (single-row) StrategySettings for the duration of the
        # transaction so concurrent approvals serialize: the check below and the
        # caller's subsequent position insert cannot interleave and both pass the
        # max_open_positions / exposure guards (no-op on SQLite).
        settings = self.settings.current_for_update()
        if not settings.is_enabled:
            return RiskDecision(False, "strategy_disabled")
        if self.positions.open_count() >= settings.max_open_positions:
            return RiskDecision(False, "max_open_positions")

        # --- TOTAL EXPOSURE GUARD ---
        # Sum existing open position values plus the proposed new notional and
        # ensure the total stays below a safe fraction of equity.
        max_total_exposure_pct = Decimal(str(get_settings().max_total_exposure_pct))
        existing_exposure = self.positions.open_notional()
        new_notional = equity * settings.max_capital_per_trade_pct
        if existing_exposure + new_notional > equity * max_total_exposure_pct:
            return RiskDecision(
                False,
                f"max_total_exposure: {existing_exposure + new_notional:.2f} > limit {equity * max_total_exposure_pct:.2f}",
            )

        daily_limit = -(equity * settings.daily_max_loss_pct)
        weekly_limit = -(equity * settings.weekly_max_loss_pct)
        if self._period_pnl(equity, day_start_utc()) <= daily_limit:
            return RiskDecision(False, "daily_loss_limit")
        if self._period_pnl(equity, week_start_utc()) <= weekly_limit:
            return RiskDecision(False, "weekly_loss_limit")

        # Risk levels first — sizing may depend on the stop distance. The stop is
        # on the LOSS side of entry and the target on the PROFIT side, mirrored by
        # direction, so shorts get a valid protective stop ABOVE entry (a long-only
        # formula would put a short's stop below entry where it can never trigger).
        stop_distance = atr_value * settings.atr_multiplier
        is_long = side != "short"
        if is_long:
            stop_loss = entry - stop_distance
            take_profit = entry + (stop_distance * settings.min_reward_risk)
            valid = stop_loss > 0 and take_profit > entry
        else:
            stop_loss = entry + stop_distance
            take_profit = entry - (stop_distance * settings.min_reward_risk)
            valid = take_profit > 0 and stop_loss > entry
        risk_per_unit = stop_distance
        if not valid or risk_per_unit <= 0:
            return RiskDecision(False, "invalid_risk_levels")

        app_settings = get_settings()
        notional_cap = equity * settings.max_capital_per_trade_pct
        if app_settings.risk_based_sizing_enabled:
            # Fixed-fractional RISK sizing: size so the loss if stopped out equals
            # max_risk_per_trade_pct of equity. Cap at the notional limit so the
            # total-exposure guard above stays valid.
            risk_budget = equity * Decimal(str(app_settings.max_risk_per_trade_pct))
            quantity = risk_budget / risk_per_unit
            if quantity * entry > notional_cap:
                quantity = notional_cap / entry
        else:
            # Notional-based: allocate `max_capital_per_trade_pct` of equity. The
            # loss if stopped out is ≈ notional * stop_distance/entry, i.e. smaller
            # than the allocated notional.
            quantity = notional_cap / entry

        # Optional volatility targeting: feed the current volatility (ATR) back
        # into sizing so per-trade risk is steadier across calm/volatile markets.
        if app_settings.vol_targeting_enabled and entry > 0 and atr_value > 0:
            mult = vol_target_multiplier(
                atr_value / entry,
                Decimal(str(app_settings.vol_target_atr_pct)),
                Decimal(str(app_settings.vol_target_min_multiplier)),
                Decimal(str(app_settings.vol_target_max_multiplier)),
            )
            quantity = quantity * mult

        # --- PER-TRADE MAXIMUM DOLLAR LOSS GUARD ---
        # Prevent a single catastrophic fill (e.g., flash crash) from exceeding
        # a hard dollar limit regardless of daily/weekly limits.
        max_loss_per_trade_pct = Decimal(str(get_settings().max_risk_per_trade_pct))
        max_loss_dollar = equity * max_loss_per_trade_pct
        max_loss_from_trade = risk_per_unit * quantity
        if max_loss_from_trade > max_loss_dollar:
            return RiskDecision(
                False,
                f"excessive_risk_per_trade: loss {max_loss_from_trade:.2f} > limit {max_loss_dollar:.2f}",
            )

        return RiskDecision(True, "approved", quantity, stop_loss, take_profit)
