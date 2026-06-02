from itertools import product

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.backtest.multiple_testing import assess_multiple_testing


class ParameterOptimizer:
    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def grid_search(self, data: pd.DataFrame, base_config: BacktestConfig, grid: dict[str, list]) -> list[dict]:
        keys = list(grid.keys())
        results: list[dict] = []
        for values in product(*(grid[key] for key in keys)):
            params = {**base_config.parameters, **dict(zip(keys, values))}
            config = BacktestConfig(**{**base_config.__dict__, "parameters": params})
            result = self.engine.run(data, config)
            metrics = result["metrics"]
            results.append(
                {
                    "parameters": params,
                    "net_profit": metrics.get("net_profit", 0),
                    "max_drawdown": metrics.get("max_drawdown", 0),
                    "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                    "total_trades": metrics.get("total_trades", 0),
                }
            )
        ranked = sorted(
            results,
            key=lambda item: (
                item["net_profit"],
                item["sharpe_ratio"],
                -abs(item["max_drawdown"]),
            ),
            reverse=True,
        )
        # Flag selection bias: the best of N trials is inflated by multiple testing.
        if ranked:
            ranked[0]["multiple_testing"] = assess_multiple_testing(
                [r["sharpe_ratio"] for r in ranked]
            )
        return ranked

    def walk_forward(
        self, data: pd.DataFrame, base_config: BacktestConfig, windows: list[dict], grid: dict[str, list]
    ) -> list[dict]:
        output: list[dict] = []
        for window in windows:
            train = data[(data.index >= window["train_start"]) & (data.index <= window["train_end"])]
            test = data[(data.index >= window["test_start"]) & (data.index <= window["test_end"])]
            optimization = self.grid_search(train, base_config, grid)
            best = optimization[0]["parameters"] if optimization else base_config.parameters
            test_config = BacktestConfig(**{**base_config.__dict__, "parameters": best})
            result = self.engine.run(test, test_config)
            output.append(
                {
                    "train_start": str(window["train_start"]),
                    "train_end": str(window["train_end"]),
                    "test_start": str(window["test_start"]),
                    "test_end": str(window["test_end"]),
                    "best_parameters": best,
                    "test_metrics": result["metrics"],
                }
            )
        return output
