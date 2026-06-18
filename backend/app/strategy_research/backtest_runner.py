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
        """k-fold PURGED cross-validation for overfit detection.

        Splits data into `folds` sequential chunks. For each fold:
          - IS = data before the fold (expanding training set)
          - OOS = the fold itself (next contiguous chunk)
        A PURGE GAP (embargo) of `research_cv_folds_purge_bars` bars is dropped
        between the IS block and the OOS fold on BOTH sides — this is the
        López de Prado leakage-prevention technique the walk-forward splitter
        already uses. Without it, adjacent train/test chunks share
        autocorrelation (a position held across the boundary leaks returns),
        understating overfit. "Purged CV" must actually purge.

        Overfit is flagged when mean(OOS Sharpe) < 0.5 * mean(IS Sharpe).
        """
        n = len(data)
        if n < MIN_CANDLES * (folds + 1) or folds < 2:
            return 0.0, [], False

        # Purge gap in bars: ~ the longest indicator lookback (e.g. 200 for
        # EMA200) so a position held into the OOS fold does not leak IS alpha.
        # Default to a sensible floor if the config is missing.
        purge = int(getattr(self.settings, "research_cv_purge_bars", 0) or 200)

        is_sharpes: list[float] = []
        oos_sharpes: list[float] = []
        fold_size = n // (folds + 1)

        for k in range(1, folds + 1):
            is_end = k * fold_size
            oos_start = k * fold_size
            # Drop `purge` bars between IS and OOS on both sides.
            is_data = data.iloc[: max(is_end - purge, 0)]
            oos_data = data.iloc[oos_start + purge : (k + 1) * fold_size - purge]
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
        """Harvey-Liu Deflated Sharpe Ratio p-value.

        Returns the probability that the observed Sharpe is a spurious maximum
        from multiple testing — i.e. the probability under the null that the
        BEST of N trials reaches at least the observed Sharpe. Lower p-values
        => the observed Sharpe is unlikely to be chance and is more trustworthy.

        Implementation (Bailey & López de Prado 2014, "The Deflated Sharpe
        Ratio"):
          1. Compute the expected maximum Sharpe under the null (E[max] over N
             trials with Sharpe std `σ_SR`): E[max] ≈ σ_SR·[(1-γ)·Z⁻¹(1-1/N) +
             γ·Z⁻¹(1-1/(N·e))].
          2. Deflate the observed Sharpe by subtracting E[max]: SR* = SR − E[max].
          3. The DSR p-value = Φ(SR* / σ_SR): how likely a single trial under
             the null reaches the deflated Sharpe. (One-sided: smaller is more
             significant.)

        The previous implementation returned `Φ(z)^N` (the probability that ALL
        N trials are below z), which is not the DSR — it conflated the
        selection-bias test with a joint CDF and produced misleadingly high
        "p-values" for good strategies. This uses the proper deflation.
        """
        if observed_sharpe <= 0:
            return 1.0  # no edge to deflate; maximum spuriousness probability
        n_trials = n_trials or self.settings.research_population
        var_sharpe = var_sharpe or (1.0 / self.settings.research_min_trades)
        se = math.sqrt(var_sharpe) if var_sharpe > 0 else 0.0
        if se <= 0 or n_trials < 2:
            # Too few trials or no variance: cannot assess selection bias.
            # Return a conservative high p-value (do not trust a single shot).
            return 1.0
        # Expected max Sharpe under the null over n_trials.
        from app.backtest.multiple_testing import expected_max_sharpe

        exp_max = expected_max_sharpe(n_trials, se)
        # Deflate: subtract the expected-max bias.
        deflated = observed_sharpe - exp_max
        # p-value = P(SR_null >= deflated) = 1 - Φ(deflated / se).
        try:
            from scipy import stats

            pvalue = float(1.0 - stats.norm.cdf(deflated / se))
        except ImportError:
            z = deflated / se
            pvalue = float(0.5 * (1.0 - math.erf(z / math.sqrt(2))))
        return round(min(max(pvalue, 0.0), 1.0), 6)

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
