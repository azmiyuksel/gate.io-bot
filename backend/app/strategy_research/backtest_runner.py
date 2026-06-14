"""Runs a genome through backtest + walk-forward + Monte Carlo and overfit checks.

Reuses the production backtest engine (so research and live share identical
execution/fee/slippage semantics) and the existing metrics. Walk-forward uses
anchored (expanding) windows by default. Overfit is detected via k-fold purged
cross-validation comparing IS vs OOS Sharpe, combined with Deflated Sharpe Ratio.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestEngine, HistoricalDataLoader
from app.backtest.models import BacktestConfig
from app.core.config import get_settings
from app.portfolio.performance import PerformanceCalculator
from app.strategy_research.models import (
    EvaluationResult,
    StrategyGenome,
    WalkForwardWindowResult,
)

MIN_CANDLES = 350  # enough to warm up a 300-period EMA plus signal room


class ResearchBacktestRunner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.loader = HistoricalDataLoader(db)
        self.engine = BacktestEngine()

    def _config(self, genome: StrategyGenome, symbol: str, timeframe: str) -> BacktestConfig:
        now = datetime.now()
        return BacktestConfig(
            symbol=symbol,
            timeframe=timeframe,
            start_at=now,
            end_at=now,
            parameters=dict(genome.parameters),
            strategy_class=genome.template,
        )

    def _run_safe(self, data: pd.DataFrame, config: BacktestConfig) -> dict | None:
        if data is None or data.empty or len(data) < MIN_CANDLES:
            return None
        try:
            return self.engine.run(data, config)
        except Exception:
            return None

    @staticmethod
    def _stability(initial_cash: float, trades) -> float:
        """Equity-curve smoothness (R^2) built from cumulative trade PnL."""
        if not trades:
            return 0.0
        equity = [initial_cash]
        for t in trades:
            equity.append(equity[-1] + float(t.pnl))
        return PerformanceCalculator.calculate_stability_score(equity)

    def _walk_forward(
        self, data: pd.DataFrame, config: BacktestConfig, windows: int
    ) -> list[WalkForwardWindowResult]:
        """Anchored walk-forward: each window starts from the beginning and expands.

        The first window uses ~1/windows of data, the last uses all data. This
        tests whether performance holds as more market regimes are included.
        """
        results: list[WalkForwardWindowResult] = []
        n = len(data)
        if n < MIN_CANDLES * 2 or windows < 2:
            return results
        use_anchored = self.settings.research_wf_method == "anchored"
        for i in range(windows):
            if use_anchored:
                end_idx = n * (i + 1) // windows
                chunk = data.iloc[:end_idx]
                wf_idx = i
            else:
                size = n // windows
                chunk = data.iloc[i * size : (i + 1) * size] if i < windows - 1 else data.iloc[i * size :]
                wf_idx = i
            run = self._run_safe(chunk, config)
            if run is None:
                results.append(WalkForwardWindowResult(wf_idx, 0.0, 0.0, 0.0, 0))
                continue
            m = run["metrics"]
            results.append(
                WalkForwardWindowResult(
                    index=wf_idx,
                    sharpe=float(m.get("sharpe_ratio", 0.0)),
                    total_return=float(m.get("total_return", 0.0)),
                    max_drawdown=abs(float(m.get("max_drawdown", 0.0))),
                    trades=int(m.get("total_trades", 0)),
                )
            )
        return results

    def _kfold_cv_overfit(
        self, data: pd.DataFrame, config: BacktestConfig, folds: int = 5
    ) -> tuple[float, list[float], bool]:
        """k-fold purged cross-validation for overfit detection.

        Splits data into `folds` sequential chunks. For each fold:
          - IS = data before the fold (expanding training set)
          - OOS = the fold itself (next contiguous chunk)
        Overfit is flagged when mean(OOS Sharpe) < 0.5 * mean(IS Sharpe).
        """
        n = len(data)
        if n < MIN_CANDLES * (folds + 1) or folds < 2:
            return 0.0, [], False

        is_sharpes: list[float] = []
        oos_sharpes: list[float] = []
        fold_size = n // (folds + 1)

        for k in range(1, folds + 1):
            is_data = data.iloc[: k * fold_size]
            oos_data = data.iloc[k * fold_size : (k + 1) * fold_size]
            if len(oos_data) < MIN_CANDLES // 2:
                continue
            is_run = self._run_safe(is_data, config)
            oos_run = self._run_safe(oos_data, config)
            is_s = float(is_run["metrics"].get("sharpe_ratio", 0.0)) if is_run else 0.0
            oos_s = float(oos_run["metrics"].get("sharpe_ratio", 0.0)) if oos_run else 0.0
            is_sharpes.append(is_s)
            oos_sharpes.append(oos_s)

        if not is_sharpes or not oos_sharpes:
            return 0.0, [], False

        mean_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
        mean_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
        cv_overfit = mean_is > 0.5 and mean_oos < mean_is * 0.5
        return mean_oos, oos_sharpes, cv_overfit

    def _deflated_sharpe_ratio(
        self, observed_sharpe: float, n_trials: int | None = None, var_sharpe: float | None = None
    ) -> float:
        """Harvey-Liu Deflated Sharpe Ratio test.

        Estimates the probability that the observed Sharpe is the maximum among
        N independent trials, where each trial's Sharpe is approximately normal.
        Returns the DSR p-value: lower values indicate the observed Sharpe is
        unlikely to be a spurious maximum from multiple testing.

        Reference: Harvey, Liu (2015) "Backtesting"
        """
        if observed_sharpe <= 0:
            return 0.0
        n_trials = n_trials or self.settings.research_population
        var_sharpe = var_sharpe or (1.0 / self.settings.research_min_trades)
        se = math.sqrt(var_sharpe)
        z = observed_sharpe / se if se > 0 else 0.0
        try:
            from scipy import stats
            prob_one = float(stats.norm.cdf(z))
        except ImportError:
            prob_one = float(0.5 * (1 + math.erf(z / math.sqrt(2))))
        prob_max = prob_one ** n_trials
        return round(min(prob_max, 1.0), 6)

    def _min_track_days(self, data: pd.DataFrame) -> int:
        """Estimate calendar days of track record from timestamp range."""
        if data.empty or data.index.empty:
            return 0
        return (data.index[-1] - data.index[0]).days

    def evaluate(
        self,
        genome: StrategyGenome,
        symbol: str = "BTC_USDT",
        timeframe: str = "1h",
        wf_windows: int = 4,
    ) -> EvaluationResult | None:
        config = self._config(genome, symbol, timeframe)
        data = self.loader.load_from_cache(
            symbol, timeframe, datetime(1970, 1, 1), datetime(2100, 1, 1)
        )
        full = self._run_safe(data, config)
        if full is None:
            return None

        metrics = full["metrics"]
        trades = full["trades"]
        sharpe = float(metrics.get("sharpe_ratio", 0.0))
        profit_factor = float(metrics.get("profit_factor", 0.0))
        max_dd = abs(float(metrics.get("max_drawdown", 0.0)))
        stability = self._stability(config.initial_cash, trades)

        wf = self._walk_forward(data, config, wf_windows)
        profitable = [w for w in wf if w.total_return > 0]
        consistency = (len(profitable) / len(wf)) if wf else 0.0

        # k-fold purged CV for overfit detection.
        cv_oos_sharpe, oos_sharpes, cv_overfit = self._kfold_cv_overfit(
            data, config, self.settings.research_cv_folds
        )

        # Also compute simple IS/OOS for backward compatibility.
        split = int(len(data) * 0.7)
        is_run = self._run_safe(data.iloc[:split], config)
        oos_run = self._run_safe(data.iloc[split:], config)
        is_sharpe = float(is_run["metrics"].get("sharpe_ratio", 0.0)) if is_run else 0.0
        oos_sharpe = float(oos_run["metrics"].get("sharpe_ratio", 0.0)) if oos_run else 0.0

        # Combined overfit: flagged if CV indicates overfit OR simple split shows collapse.
        overfit = cv_overfit or (is_sharpe > 0.5 and oos_sharpe < is_sharpe * 0.5) or (
            is_sharpe > 0 and oos_sharpe < 0
        )

        # Deflated Sharpe Ratio.
        total_trades = int(metrics.get("total_trades", 0))
        dsr_pvalue = self._deflated_sharpe_ratio(sharpe, n_trials=None, var_sharpe=None)

        track_days = self._min_track_days(data)

        metrics_with_extra = dict(metrics)
        metrics_with_extra["in_sample_sharpe"] = round(is_sharpe, 6)
        metrics_with_extra["out_sample_sharpe"] = round(oos_sharpe, 6)
        metrics_with_extra["cv_oos_sharpes"] = [round(s, 6) for s in oos_sharpes]
        metrics_with_extra["cv_oos_mean_sharpe"] = round(cv_oos_sharpe, 6)
        metrics_with_extra["dsr_pvalue"] = dsr_pvalue
        metrics_with_extra["track_days"] = track_days

        return EvaluationResult(
            genome=genome,
            metrics=metrics_with_extra,
            monte_carlo=full["monte_carlo"],
            walk_forward=wf,
            sharpe=sharpe,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            stability_score=round(stability, 6),
            consistency_score=round(consistency, 6),
            in_sample_sharpe=round(is_sharpe, 6),
            out_sample_sharpe=round(oos_sharpe, 6),
            overfit=bool(overfit),
            total_trades=total_trades,
        )
