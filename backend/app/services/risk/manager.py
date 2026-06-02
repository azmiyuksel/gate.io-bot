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


def vol_target_multiplier(
    atr_pct: Decimal, target_pct: Decimal, min_mult: Decimal, max_mult: Decimal
) -> Decimal:
    """Volatility-targeting size multiplier: scale inversely to volatility so
    per-trade risk stays roughly constant, bounded to avoid extreme sizing.

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
        settings = self.settings.current()
        if not settings.is_enabled:
            return RiskDecision(False, "strategy_disabled")
        if self.positions.open_count() >= settings.max_open_positions:
            return RiskDecision(False, "max_open_positions")

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

        return RiskDecision(True, "approved", quantity, stop_loss, take_profit)
