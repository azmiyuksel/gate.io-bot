from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PaperStartRequest(BaseModel):
    account_name: str = "default"
    initial_balance: Decimal = Decimal("10000")
    symbols: list[str] = ["BTC_USDT", "ETH_USDT"]


class PaperStatus(BaseModel):
    account_id: int
    status: str
    cash_balance: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    exposure: Decimal
    metrics: dict


class PaperPositionOut(BaseModel):
    id: int
    symbol: str
    quantity: Decimal
    average_entry_price: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    is_open: bool

    model_config = {"from_attributes": True}


class PaperTradeOut(BaseModel):
    id: int
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    realized_pnl: Decimal
    traded_at: datetime

    model_config = {"from_attributes": True}


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
