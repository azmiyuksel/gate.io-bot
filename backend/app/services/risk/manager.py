from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.repositories.trading import PositionRepository, StrategySettingsRepository, TradeRepository


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
        self.positions = PositionRepository(db)
        self.trades = TradeRepository(db)
        self.settings = StrategySettingsRepository(db)

    def approve_entry(self, equity: Decimal, entry: Decimal, atr_value: Decimal) -> RiskDecision:
        # Master env kill-switch: live entries require BOT_ENABLED=true as well
        # as the strategy's own enable flag (defense-in-depth alongside scheduler).
        if not get_settings().bot_enabled:
            return RiskDecision(False, "bot_disabled")
        if entry <= 0 or atr_value <= 0:
            return RiskDecision(False, "invalid_price_data")
        settings = self.settings.current()
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
        if self.trades.daily_pnl() <= daily_limit:
            return RiskDecision(False, "daily_loss_limit")
        if self.trades.weekly_pnl() <= weekly_limit:
            return RiskDecision(False, "weekly_loss_limit")

        # Sizing is NOTIONAL-based: allocate `max_capital_per_trade_pct` of equity
        # to the position. This is deliberately conservative (capital preservation)
        # and is NOT a fixed "risk-to-stop" model — the loss if stopped out is far
        # smaller than the allocated notional (≈ notional * stop_distance/entry).
        notional = equity * settings.max_capital_per_trade_pct
        quantity = notional / entry

        # Optional volatility targeting: feed the current volatility (ATR) back
        # into sizing so per-trade risk is steadier across calm/volatile markets.
        app_settings = get_settings()
        if app_settings.vol_targeting_enabled and entry > 0 and atr_value > 0:
            mult = vol_target_multiplier(
                atr_value / entry,
                Decimal(str(app_settings.vol_target_atr_pct)),
                Decimal(str(app_settings.vol_target_min_multiplier)),
                Decimal(str(app_settings.vol_target_max_multiplier)),
            )
            quantity = quantity * mult

        stop_loss = entry - (atr_value * settings.atr_multiplier)
        risk_per_unit = entry - stop_loss
        take_profit = entry + (risk_per_unit * settings.min_reward_risk)
        if stop_loss <= 0 or take_profit <= entry:
            return RiskDecision(False, "invalid_risk_levels")

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
