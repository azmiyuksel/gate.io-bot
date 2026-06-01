from datetime import UTC, datetime

import pandas as pd

from app.backtest.engine import BacktestEngine
from app.backtest.models import BacktestConfig
from app.walkforward.metrics import aggregate_results, monte_carlo_wfa, walk_forward_efficiency
from app.walkforward.models import WalkForwardConfig, WalkForwardWindowResult
from app.walkforward.optimizer import WalkForwardOptimizer
from app.walkforward.report import build_walkforward_report
from app.walkforward.splitter import TimeSeriesSplitter
from app.walkforward.validator import WalkForwardValidator


class WalkForwardEngine:
    def __init__(
        self,
        splitter: TimeSeriesSplitter | None = None,
        optimizer: WalkForwardOptimizer | None = None,
        validator: WalkForwardValidator | None = None,
    ) -> None:
        self.splitter = splitter or TimeSeriesSplitter()
        self.optimizer = optimizer or WalkForwardOptimizer()
        self.validator = validator or WalkForwardValidator()
        self.backtest_engine = BacktestEngine()

    def run(self, data: pd.DataFrame, config: WalkForwardConfig) -> dict:
        windows = self.splitter.split(data, config)
        if not windows:
            raise ValueError("No valid walk-forward windows for the selected data range")
        results: list[WalkForwardWindowResult] = []
        combined_equity = []
        combined_trades: list[dict] = []
        overfit_messages: list[dict] = []
        for spec in windows:
            train_data = data[(data.index >= spec.train_start) & (data.index < spec.train_end)]
            test_data = data[(data.index >= spec.test_start) & (data.index < spec.test_end)]
            if train_data.empty or test_data.empty:
                continue
            best_params, train_result = self.optimizer.optimize(train_data, config)
            test_result = self._run_test(test_data, config, best_params)
            train_metrics = train_result["metrics"]
            test_metrics = test_result["metrics"]
            wfe = walk_forward_efficiency(
                float(train_metrics.get("net_profit", 0)),
                float(test_metrics.get("net_profit", 0)),
            )
            warning, messages = self.validator.detect_overfit(train_metrics, test_metrics)
            if warning:
                overfit_messages.append({"window_id": spec.window_id, "warnings": messages})
            trades = [
                {
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "entry_time": trade.entry_time.isoformat(),
                    "exit_time": trade.exit_time.isoformat(),
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "exit_reason": trade.exit_reason,
                }
                for trade in test_result["trades"]
            ]
            result = WalkForwardWindowResult(
                window_id=spec.window_id,
                train_start=spec.train_start,
                train_end=spec.train_end,
                test_start=spec.test_start,
                test_end=spec.test_end,
                best_params=best_params,
                train_metrics=train_metrics,
                test_metrics=test_metrics,
                equity_curve=self._normalize_equity(test_result["charts"], test_result, combined_equity),
                trades=trades,
                wfe=wfe,
                overfit_warning=warning,
            )
            results.append(result)
            combined_equity.extend(result.equity_curve)
            combined_trades.extend(trades)
        if not results:
            raise ValueError("Walk-forward windows did not produce any results")
        aggregated = aggregate_results(results)
        mc = monte_carlo_wfa(combined_trades, config.initial_cash, scenarios=1000)
        deployment = self.validator.deployment_decision(aggregated, bool(overfit_messages))
        report = build_walkforward_report(aggregated, results, combined_equity)
        return {
            "windows": results,
            "aggregated_metrics": aggregated,
            "combined_equity_curve": combined_equity,
            "monte_carlo_results": mc,
            "deployment_decision": deployment,
            "overfit_warnings": overfit_messages,
            "report": report,
            "completed_at": datetime.now(UTC),
        }

    def _run_test(self, test_data: pd.DataFrame, config: WalkForwardConfig, params: dict) -> dict:
        return self.backtest_engine.run(
            test_data,
            BacktestConfig(
                symbol=config.symbol,
                timeframe=config.timeframe,
                start_at=config.start_at,
                end_at=config.end_at,
                initial_cash=config.initial_cash,
                max_open_positions=int(params.get("max_open_positions", 3)),
                max_capital_per_trade_pct=float(params.get("max_capital_per_trade_pct", 0.01)),
                parameters=params,
            ),
        )

    def _normalize_equity(self, charts: dict, test_result: dict, previous: list[dict]) -> list[dict]:
        # Backtest engine stores the usable curve in chart JSON only for UI, so use metric-preserving
        # synthetic points from trades when raw equity curve is not exposed.
        trades = test_result["trades"]
        base = previous[-1]["equity"] if previous else 10_000
        points = []
        equity = base
        for trade in trades:
            equity += trade.pnl
            points.append({"timestamp": trade.exit_time.isoformat(), "equity": equity})
        return points or [{"timestamp": datetime.now(UTC).isoformat(), "equity": base}]
