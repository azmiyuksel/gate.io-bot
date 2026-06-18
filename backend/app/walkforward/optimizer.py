import tempfile
from pathlib import Path

import optuna
import pandas as pd
from joblib import Memory
from sklearn.model_selection import ParameterGrid

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.walkforward.metrics import objective_score
from app.walkforward.models import WalkForwardConfig

_cache_dir = Path(tempfile.gettempdir()) / "gatebot_wfa_cache"
memory = Memory(location=str(_cache_dir), verbose=0)


class WalkForwardOptimizer:
    def __init__(self, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def _suggest_params(self, trial: optuna.Trial, config: WalkForwardConfig) -> dict:
        """Suggest a parameter set matching the strategy being optimized.

        The search space MUST align with the strategy the run validates —
        optimizing EMA/RSI parameters while the live strategy trades a
        Donchian breakout validated nothing. Each strategy gets its own space.
        """
        cls = config.strategy_class
        if cls == "momentum_breakout_v1":
            # Momentum/breakout parameters (mirror momentum_breakout.py +
            # MomentumBreakoutBacktestStrategy). These are what the live
            # momentum strategy actually uses.
            return {
                **config.base_parameters,
                "ema_fast": trial.suggest_int("ema_fast", 5, 20),
                "ema_slow": trial.suggest_int("ema_slow", 15, 50),
                "ema_trend": trial.suggest_int("ema_trend", 30, 100),
                "donchian_lookback": trial.suggest_int("donchian_lookback", 10, 40),
                "vol_spike_mult": trial.suggest_float("vol_spike_mult", 1.1, 2.0),
                "rsi_long_max": trial.suggest_float("rsi_long_max", 70, 90),
                "min_atr_pct": trial.suggest_float("min_atr_pct", 0.001, 0.005),
                "breakout_buffer_atr": trial.suggest_float("breakout_buffer_atr", 0.02, 0.2),
                "atr_multiplier": trial.suggest_float("atr_multiplier", 1.2, 3.5),
                "reward_risk": trial.suggest_float("reward_risk", 1.0, 3.0),
                "max_risk_per_trade_pct": trial.suggest_float("risk_percent", 0.005, 0.02),
            }
        # capital_preservation_v1 and the generic ema_rsi_atr/macd/bollinger
        # strategies: keep the classic EMA/RSI/ATR search space.
        return {
            **config.base_parameters,
            "ema_entry": trial.suggest_int("ema_fast", 10, 50),
            "ema_trend": trial.suggest_int("ema_slow", 100, 250),
            "rsi_period": trial.suggest_int("rsi_period", 10, 21),
            "rsi_threshold": trial.suggest_float("rsi_entry", 25, 40),
            "atr_multiplier": trial.suggest_float("atr_multiplier", 1.2, 3.0),
            "max_capital_per_trade_pct": trial.suggest_float("risk_percent", 0.0025, 0.02),
        }

    def optimize(self, train_data: pd.DataFrame, config: WalkForwardConfig) -> tuple[dict, dict]:
        cls = config.strategy_class

        def objective(trial: optuna.Trial) -> float:
            params = self._suggest_params(trial, config)
            # For the classic EMA strategy, fast must be < slow to be meaningful.
            if cls != "momentum_breakout_v1" and params.get("ema_entry", 0) >= params.get("ema_trend", 0):
                raise optuna.TrialPruned()
            result = self._run(train_data, config, params)
            return objective_score(result["metrics"])

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=config.n_trials, show_progress_bar=False)
        best_params = {**config.base_parameters, **study.best_params}
        # Map the optuna param names back to the strategy's expected keys.
        if cls == "momentum_breakout_v1":
            best_params = {
                **config.base_parameters,
                "ema_fast": study.best_params["ema_fast"],
                "ema_slow": study.best_params["ema_slow"],
                "ema_trend": study.best_params["ema_trend"],
                "donchian_lookback": study.best_params["donchian_lookback"],
                "vol_spike_mult": study.best_params["vol_spike_mult"],
                "rsi_long_max": study.best_params["rsi_long_max"],
                "min_atr_pct": study.best_params["min_atr_pct"],
                "breakout_buffer_atr": study.best_params["breakout_buffer_atr"],
                "atr_multiplier": study.best_params["atr_multiplier"],
                "reward_risk": study.best_params["reward_risk"],
                "max_risk_per_trade_pct": study.best_params["risk_percent"],
            }
        else:
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
            # Bind the backtest to the same strategy class the run validates.
            strategy_class=config.strategy_class,
        )
        return self.engine.run(data, backtest_config)
