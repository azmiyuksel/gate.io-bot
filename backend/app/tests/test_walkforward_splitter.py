from datetime import datetime

import pandas as pd

from app.walkforward.models import SplitMode, WalkForwardConfig
from app.walkforward.splitter import TimeSeriesSplitter


def test_rolling_splitter_uses_time_ordered_windows() -> None:
    data = pd.DataFrame(
        {"close": [1] * 500},
        index=pd.date_range("2022-01-01", periods=500, freq="1D", tz="UTC"),
    )
    config = WalkForwardConfig(
        symbol="BTC_USDT",
        timeframe="1d",
        start_at=datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        end_at=datetime.fromisoformat("2023-05-01T00:00:00+00:00"),
        mode=SplitMode.rolling,
        train_period_days=120,
        test_period_days=30,
        step_days=30,
    )
    windows = TimeSeriesSplitter().split(data, config)
    assert windows
    assert windows[0].train_start < windows[0].train_end <= windows[0].test_start
    assert windows[1].train_start > windows[0].train_start


def test_expanding_splitter_keeps_initial_train_start() -> None:
    data = pd.DataFrame(
        {"close": [1] * 500},
        index=pd.date_range("2022-01-01", periods=500, freq="1D", tz="UTC"),
    )
    config = WalkForwardConfig(
        symbol="BTC_USDT",
        timeframe="1d",
        start_at=datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        end_at=datetime.fromisoformat("2023-05-01T00:00:00+00:00"),
        mode=SplitMode.expanding,
        train_period_days=120,
        test_period_days=30,
        step_days=30,
    )
    windows = TimeSeriesSplitter().split(data, config)
    assert windows[0].train_start == windows[1].train_start
    assert windows[1].train_end > windows[0].train_end
