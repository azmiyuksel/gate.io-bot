from decimal import Decimal

from pydantic import BaseModel, field_validator


class PositionOut(BaseModel):
    id: int
    symbol: str
    status: str
    side: str
    entry_price: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    trailing_stop: Decimal | None = None
    breakeven_stop: bool = False
    realized_pnl: Decimal
    # Exchange-side stop state — critical for the operator to see whether a
    # position is PROTECTED (resting exchange stop) or DEGRADED (local poll only,
    # needs a manual stop). None = no exchange stop placed.
    exchange_stop_order_id: str | None = None
    stop_placed_at: str | None = None
    opened_at: str | None = None

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

    @field_validator("max_capital_per_trade_pct")
    @classmethod
    def validate_max_capital_pct(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= 0 or v > Decimal("0.20")):
            raise ValueError("max_capital_per_trade_pct must be between 0 (exclusive) and 20%")
        return v

    @field_validator("daily_max_loss_pct")
    @classmethod
    def validate_daily_loss_pct(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= 0 or v > Decimal("0.10")):
            raise ValueError("daily_max_loss_pct must be between 0 (exclusive) and 10%")
        return v

    @field_validator("weekly_max_loss_pct")
    @classmethod
    def validate_weekly_loss_pct(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= 0 or v > Decimal("0.30")):
            raise ValueError("weekly_max_loss_pct must be between 0 (exclusive) and 30%")
        return v

    @field_validator("max_open_positions")
    @classmethod
    def validate_max_open_positions(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 20):
            raise ValueError("max_open_positions must be between 1 and 20")
        return v

    @field_validator("atr_multiplier")
    @classmethod
    def validate_atr_multiplier(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= 0 or v > Decimal("10")):
            raise ValueError("atr_multiplier must be between 0 (exclusive) and 10")
        return v

    @field_validator("trailing_stop_pct")
    @classmethod
    def validate_trailing_stop_pct(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and (v <= 0 or v >= Decimal("1")):
            raise ValueError("trailing_stop_pct must be between 0 (exclusive) and 100% (exclusive)")
        return v


class DashboardSummary(BaseModel):
    total_balance: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    bot_enabled: bool
    open_positions: list[PositionOut]
    recent_trades: list[TradeOut]
    strategy: StrategySettingsOut
