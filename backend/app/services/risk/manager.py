from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.trading import PositionRepository, StrategySettingsRepository, TradeRepository


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    quantity: Decimal = Decimal("0")
    stop_loss: Decimal = Decimal("0")
    take_profit: Decimal = Decimal("0")


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

        notional = equity * settings.max_capital_per_trade_pct
        quantity = notional / entry
        stop_loss = entry - (atr_value * settings.atr_multiplier)
        risk_per_unit = entry - stop_loss
        take_profit = entry + (risk_per_unit * settings.min_reward_risk)
        if stop_loss <= 0 or take_profit <= entry:
            return RiskDecision(False, "invalid_risk_levels")

        return RiskDecision(True, "approved", quantity, stop_loss, take_profit)
