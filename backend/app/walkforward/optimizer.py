import optuna
import pandas as pd
from joblib import Memory
from sklearn.model_selection import ParameterGrid

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.walkforward.metrics import objective_score
from app.walkforward.models import WalkForwardConfig

memory = Memory(location="/tmp/gatebot_wfa_cache", verbose=0)


class WalkForwardOptimizer:
    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def optimize(self, train_data: pd.DataFrame, config: WalkForwardConfig) -> tuple[dict, dict]:
        def objective(trial: optuna.Trial) -> float:
            params = {
                **config.base_parameters,
                "ema_entry": trial.suggest_int("ema_fast", 10, 50),
                "ema_trend": trial.suggest_int("ema_slow", 100, 250),
                "rsi_period": trial.suggest_int("rsi_period", 10, 21),
                "rsi_threshold": trial.suggest_float("rsi_entry", 25, 40),
                "atr_multiplier": trial.suggest_float("atr_multiplier", 1.2, 3.0),
                "max_capital_per_trade_pct": trial.suggest_float("risk_percent", 0.0025, 0.02),
            }
            if params["ema_entry"] >= params["ema_trend"]:
                raise optuna.TrialPruned()
            result = self._run(train_data, config, params)
            return objective_score(result["metrics"])

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=config.n_trials, show_progress_bar=False)
        best_params = {
            **config.base_parameters,
            "ema_entry": study.best_params["ema_fast"],
            "ema_trend": study.best_params["ema_slow"],
            "rsi_period": study.best_params["rsi_period"],
            "rsi_threshold": study.best_params["rsi_entry"],
            "atr_multiplier": study.best_params["atr_multiplier"],
            "max_capital_per_trade_pct": study.best_params["risk_percent"],
        }
        train_result = self._run(train_data, config, best_params)
        return best_params, train_result

    def coarse_grid(self) -> list[dict]:
        return list(
            ParameterGrid(
                {
                    "ema_entry": [10, 20, 30],
                    "ema_trend": [100, 150, 200],
                    "rsi_period": [14],
                    "rsi_threshold": [25, 30, 35],
                    "atr_multiplier": [1.5, 2.0, 2.5],
                    "max_capital_per_trade_pct": [0.005, 0.01],
                }
            )
        )

    def _run(self, data: pd.DataFrame, config: WalkForwardConfig, params: dict) -> dict:
        backtest_config = BacktestConfig(
            symbol=config.symbol,
            timeframe=config.timeframe,
            start_at=config.start_at,
            end_at=config.end_at,
            initial_cash=config.initial_cash,
            max_open_positions=int(params.get("max_open_positions", 3)),
            max_capital_per_trade_pct=float(params.get("max_capital_per_trade_pct", 0.01)),
            parameters=params,
        )
        return self.engine.run(data, backtest_config)
