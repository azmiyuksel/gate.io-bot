from decimal import Decimal

from pydantic import BaseModel


class PositionOut(BaseModel):
    id: int
    symbol: str
    status: str
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    realized_pnl: Decimal

    model_config = {"from_attributes": True}


class TradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    realized_pnl: Decimal

    model_config = {"from_attributes": True}


class StrategySettingsOut(BaseModel):
    is_enabled: bool
    max_capital_per_trade_pct: Decimal
    daily_max_loss_pct: Decimal
    weekly_max_loss_pct: Decimal
    max_open_positions: int
    min_reward_risk: Decimal
    atr_multiplier: Decimal
    trailing_stop_pct: Decimal

    model_config = {"from_attributes": True}


class StrategySettingsUpdate(BaseModel):
    is_enabled: bool | None = None
    max_capital_per_trade_pct: Decimal | None = None
    daily_max_loss_pct: Decimal | None = None
    weekly_max_loss_pct: Decimal | None = None
    max_open_positions: int | None = None
    atr_multiplier: Decimal | None = None
    trailing_stop_pct: Decimal | None = None


class DashboardSummary(BaseModel):
    total_balance: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    bot_enabled: bool
    open_positions: list[PositionOut]
    recent_trades: list[TradeOut]
    strategy: StrategySettingsOut
