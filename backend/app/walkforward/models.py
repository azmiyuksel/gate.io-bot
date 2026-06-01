from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SplitMode(StrEnum):
    rolling = "rolling"
    expanding = "expanding"


@dataclass(frozen=True)
class WalkForwardConfig:
    symbol: str
    timeframe: str
    start_at: datetime
    end_at: datetime
    mode: SplitMode = SplitMode.rolling
    train_period_days: int = 365
    test_period_days: int = 90
    step_days: int = 90
    n_trials: int = 30
    initial_cash: float = 10_000
    base_parameters: dict = field(default_factory=dict)


@dataclass(frozen=True)
class WalkForwardWindowSpec:
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


@dataclass
class WalkForwardWindowResult:
    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    best_params: dict
    train_metrics: dict
    test_metrics: dict
    equity_curve: list[dict]
    trades: list[dict]
    wfe: float
    overfit_warning: bool
