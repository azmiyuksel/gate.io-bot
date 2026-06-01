"""Runs a genome through backtest + walk-forward + Monte Carlo and overfit checks.

Reuses the production backtest engine (so research and live share identical
execution/fee/slippage semantics) and the existing metrics. Walk-forward splits
the period into consecutive out-of-sample windows; overfit is flagged by
comparing in-sample vs out-of-sample Sharpe.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestEngine, HistoricalDataLoader
from app.backtest.models import BacktestConfig
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
        self.loader = HistoricalDataLoader(db)
        self.engine = BacktestEngine()

    def _config(self, genome: StrategyGenome, symbol: str, timeframe: str) -> BacktestConfig:
        # start/end are unused by the engine itself (data is pre-sliced) but the
        # dataclass requires them.
        now = datetime.now()
        return BacktestConfig(
            symbol=symbol,
            timeframe=timeframe,
            start_at=now,
            end_at=now,
            parameters=dict(genome.parameters),
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
        results: list[WalkForwardWindowResult] = []
        n = len(data)
        if n < MIN_CANDLES * 2 or windows < 2:
            return results
        size = n // windows
        for i in range(windows):
            chunk = data.iloc[i * size : (i + 1) * size] if i < windows - 1 else data.iloc[i * size :]
            run = self._run_safe(chunk, config)
            if run is None:
                results.append(WalkForwardWindowResult(i, 0.0, 0.0, 0.0, 0))
                continue
            m = run["metrics"]
            results.append(
                WalkForwardWindowResult(
                    index=i,
                    sharpe=float(m.get("sharpe_ratio", 0.0)),
                    total_return=float(m.get("total_return", 0.0)),
                    max_drawdown=abs(float(m.get("max_drawdown", 0.0))),
                    trades=int(m.get("total_trades", 0)),
                )
            )
        return results

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
            return None  # insufficient data -> caller rejects

        metrics = full["metrics"]
        trades = full["trades"]
        sharpe = float(metrics.get("sharpe_ratio", 0.0))
        profit_factor = float(metrics.get("profit_factor", 0.0))
        max_dd = abs(float(metrics.get("max_drawdown", 0.0)))
        stability = self._stability(config.initial_cash, trades)

        wf = self._walk_forward(data, config, wf_windows)
        profitable = [w for w in wf if w.total_return > 0]
        consistency = (len(profitable) / len(wf)) if wf else 0.0

        # In-sample / out-of-sample split for overfit detection.
        split = int(len(data) * 0.7)
        is_run = self._run_safe(data.iloc[:split], config)
        oos_run = self._run_safe(data.iloc[split:], config)
        is_sharpe = float(is_run["metrics"].get("sharpe_ratio", 0.0)) if is_run else 0.0
        oos_sharpe = float(oos_run["metrics"].get("sharpe_ratio", 0.0)) if oos_run else 0.0
        overfit = (is_sharpe > 0.5 and oos_sharpe < is_sharpe * 0.5) or (
            is_sharpe > 0 and oos_sharpe < 0
        )

        return EvaluationResult(
            genome=genome,
            metrics=metrics,
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
            total_trades=int(metrics.get("total_trades", 0)),
        )
