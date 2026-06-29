from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PaperStartRequest(BaseModel):
    account_name: str = "default"
    initial_balance: Decimal = Field(default=Decimal("10000"), gt=0)
    symbols: list[str] = ["BTC_USDT", "ETH_USDT", "XRP_USDT", "DOGE_USDT", "SOL_USDT", "ADA_USDT", "LINK_USDT", "AVAX_USDT"]


class PaperStatus(BaseModel):
    account_id: int
    status: str
    cash_balance: Decimal
    equity: Decimal
    initial_balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    exposure: Decimal
    metrics: dict
    pause_reason: str | None = None


class PaperPositionOut(BaseModel):
    id: int
    symbol: str
    side: str = "buy"
    quantity: Decimal
    average_entry_price: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    initial_stop_loss: Decimal | None = None
    trailing_stop: Decimal | None = None
    breakeven_triggered: bool = False
    scaled_out: bool = False
    is_open: bool
    opened_at: datetime | None = None
    # Futures realism fields exposed to the dashboard so the screen can show
    # leverage/margin/liquidation/mark price/funding (parity with a live
    # exchange's positions panel).
    leverage: Decimal | None = None
    margin: Decimal | None = None
    liquidation_price: Decimal | None = None
    mark_price: Decimal | None = None
    position_side: str | None = None
    last_funding_rate: Decimal | None = None
    last_funding_ts: datetime | None = None

    model_config = {"from_attributes": True}


class PaperTradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    realized_pnl: Decimal
    exit_reason: str | None = None
    traded_at: datetime

    model_config = {"from_attributes": True}


class ManualOrderRequest(BaseModel):
    symbol: str
    # Literal (not free-form str) so a typo like "Buy" no longer silently
    # becomes a sell — pydantic rejects it with a 422 instead.
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    order_type: Literal["market", "limit", "stop", "stop_limit", "oco"] = "market"
    # Limit price (for limit / stop_limit / oco legs). Ignored for market orders.
    price: Decimal | None = Field(default=None, gt=0)
    # Stop trigger price (for stop / stop_limit / oco legs).
    stop_price: Decimal | None = Field(default=None, gt=0)
    # Take-profit price for OCO legs (paired with stop_price).
    take_profit: Decimal | None = Field(default=None, gt=0)
    # Time-in-force: GTC (rest), IOC (immediate-or-cancel), FOK (fill-or-kill),
    # POST (post-only / maker).
    time_in_force: Literal["GTC", "IOC", "FOK", "POST"] = "GTC"
    post_only: bool = False
    reduce_only: bool = False
    # Hedge-mode position side (None => auto from order side).
    position_side: Literal["long", "short", "net"] | None = None


class ClosePositionRequest(BaseModel):
    quantity: Decimal | None = Field(default=None, gt=0)  # None = full close
    # When true, only reduce the position (never flip / open the opposite side).
    reduce_only: bool = True


class PaperOrderOut(BaseModel):
    id: int
    symbol: str
    side: str
    order_type: str
    status: str
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_fill_price: Decimal | None
    limit_price: Decimal | None
    stop_price: Decimal | None
    fee_paid: Decimal
    latency_ms: int
    signal: dict
    time_in_force: str = "GTC"
    reduce_only: bool = False
    post_only: bool = False
    linked_order_id: int | None = None
    position_side: str | None = None
    created_at: datetime
    filled_at: datetime | None

    model_config = {"from_attributes": True}


class PaperLogOut(BaseModel):
    id: int
    level: str
    event: str
    message: str
    payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class PaperMetricsOut(BaseModel):
    realized_pnl: float
    win_rate_rolling_100: float
    rolling_sharpe: float
    drawdown: float

    model_config = {"from_attributes": True}


class PaperRiskStatusOut(BaseModel):
    max_daily_loss_pct: float
    current_daily_loss_pct: float
    max_drawdown_pct: float
    current_drawdown: float
    max_exposure_pct: float
    current_exposure: float
    max_open_positions: int
    current_open_positions: int
    status: str
