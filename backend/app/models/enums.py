from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    viewer = "viewer"


class PositionStatus(StrEnum):
    open = "open"
    closed = "closed"
    closing = "closing"


class OrderSide(StrEnum):
    buy = "buy"
    sell = "sell"


class OrderStatus(StrEnum):
    open = "open"
    filled = "filled"
    cancelled = "cancelled"
    failed = "failed"


class LogLevel(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


class BacktestStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class WalkForwardMode(StrEnum):
    rolling = "rolling"
    expanding = "expanding"


class WalkForwardStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    rejected = "rejected"


class PaperBotStatus(StrEnum):
    stopped = "STOPPED"
    running = "RUNNING"
    paused = "PAUSED"


class PaperOrderStatus(StrEnum):
    pending = "pending"
    partially_filled = "partially_filled"
    filled = "filled"
    cancelled = "cancelled"
    rejected = "rejected"


class PaperOrderType(StrEnum):
    market = "market"
    limit = "limit"
    stop_loss = "stop_loss"
    stop_limit = "stop_limit"


class RebalanceTrigger(StrEnum):
    scheduled_weekly = "scheduled_weekly"
    scheduled_monthly = "scheduled_monthly"
    volatility_spike = "volatility_spike"
    drawdown_threshold = "drawdown_threshold"
    manual = "manual"


class RebalanceStatus(StrEnum):
    completed = "completed"
    skipped = "skipped"
    failed = "failed"


class MarketRegimeType(StrEnum):
    trending_bull = "TRENDING_BULL"
    trending_bear = "TRENDING_BEAR"
    sideways = "SIDEWAYS"
    high_volatility = "HIGH_VOLATILITY"
    low_volatility = "LOW_VOLATILITY"
    breakout_phase = "BREAKOUT_PHASE"


class StrategyHealthState(StrEnum):
    active = "ACTIVE"
    degraded = "DEGRADED"
    paused = "PAUSED"
    disabled = "DISABLED"
    under_review = "UNDER_REVIEW"


class StrategyAlertLevel(StrEnum):
    green = "GREEN"
    yellow = "YELLOW"
    orange = "ORANGE"
    red = "RED"


class CircuitBreakerState(StrEnum):
    armed = "ARMED"
    tripped = "TRIPPED"


class CircuitBreakerScope(StrEnum):
    daily_loss = "DAILY_LOSS"
    weekly_loss = "WEEKLY_LOSS"
    drawdown = "DRAWDOWN"
    connectivity = "CONNECTIVITY"
    manual = "MANUAL"


class ReconcileAction(StrEnum):
    no_change = "NO_CHANGE"
    filled = "FILLED"
    partially_filled = "PARTIALLY_FILLED"
    cancelled = "CANCELLED"
    not_found = "NOT_FOUND"
    error = "ERROR"



