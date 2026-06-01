from datetime import timedelta

import pandas as pd

from app.walkforward.models import SplitMode, WalkForwardConfig, WalkForwardWindowSpec


class TimeSeriesSplitter:
    def split(self, data: pd.DataFrame, config: WalkForwardConfig) -> list[WalkForwardWindowSpec]:
        if data.empty:
            return []
        start = max(pd.Timestamp(config.start_at), data.index.min()).to_pydatetime()
        end = min(pd.Timestamp(config.end_at), data.index.max()).to_pydatetime()
        train_delta = timedelta(days=config.train_period_days)
        test_delta = timedelta(days=config.test_period_days)
        step_delta = timedelta(days=config.step_days)
        windows: list[WalkForwardWindowSpec] = []
        cursor = start
        window_id = 1
        while True:
            if config.mode == SplitMode.expanding:
                train_start = start
                train_end = cursor + train_delta
            else:
                train_start = cursor
                train_end = cursor + train_delta
            test_start = train_end
            test_end = test_start + test_delta
            if test_end > end:
                break
            windows.append(
                WalkForwardWindowSpec(
                    window_id=window_id,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )
            window_id += 1
            cursor += step_delta
        return windows
