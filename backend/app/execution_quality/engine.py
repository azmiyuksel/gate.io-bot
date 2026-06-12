from datetime import datetime, timedelta
from decimal import Decimal
import numpy as np
from sqlalchemy.orm import Session
from typing import Tuple

from app.core.config import get_settings
from app.models.entities import (
    ExecutionOrder,
    ExecutionFill,
    ExecutionMetric,
    HistoricalCandle,
    SlippageLog,
    LatencyLog,
    ExecutionReport,
)
from app.execution_quality.slippage_analyzer import SlippageAnalyzer
from app.execution_quality.fill_analyzer import FillAnalyzer
from app.execution_quality.latency_tracker import LatencyTracker
from app.execution_quality.metrics import ExecutionMetricsCalculator
from app.execution_quality.optimizer import AdaptiveExecutionOptimizer
from app.execution_quality.benchmark import ExecutionBenchmarkSystem
from app.execution_quality.tca import (
    aggregate_implementation_shortfall,
    benchmark_slippage_bps,
    implementation_shortfall,
    markout_bps,
    twap,
    vwap,
)


class ExecutionQualityEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_order(
        self,
        strategy_name: str,
        symbol: str,
        side: str,
        expected_price: Decimal,
        expected_quantity: Decimal,
        signal_time: datetime,
        submission_time: datetime,
        order_id: int | None = None,
        paper_order_id: int | None = None,
        order_type: str = "market",
    ) -> ExecutionOrder:
        """
        Records the target execution intent.
        """
        exec_order = ExecutionOrder(
            strategy_name=strategy_name,
            order_id=order_id,
            paper_order_id=paper_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            status="pending",
            expected_price=expected_price,
            expected_quantity=expected_quantity,
            signal_time=signal_time,
            submission_time=submission_time,
        )
        self.db.add(exec_order)
        self.db.commit()
        self.db.refresh(exec_order)
        return exec_order

    def record_fill(
        self,
        execution_order_id: int,
        fill_price: Decimal,
        fill_quantity: Decimal,
        fee: Decimal,
        fill_time: datetime,
        ack_time: datetime | None = None,
    ) -> ExecutionFill:
        """
        Records the actual order fill execution, computes slippage and latency,
        then updates quality scores.
        """
        exec_order = self.db.query(ExecutionOrder).filter(ExecutionOrder.id == execution_order_id).first()
        if not exec_order:
            raise ValueError(f"Execution order {execution_order_id} not found")

        # Compute slippage
        slippage_pct = SlippageAnalyzer.calculate_slippage(
            exec_order.side,
            float(exec_order.expected_price),
            float(fill_price)
        )

        # Record Fill
        fill = ExecutionFill(
            execution_order_id=execution_order_id,
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            fee=fee,
            fill_time=fill_time,
            slippage=Decimal(str(slippage_pct)),
        )
        self.db.add(fill)
        
        # Update order status
        exec_order.status = "filled" if fill_quantity >= exec_order.expected_quantity else "partially_filled"

        # Record Latency logs
        used_ack_time = ack_time or exec_order.submission_time + timedelta(milliseconds=120)
        latencies = LatencyTracker.calculate_latencies(
            exec_order.signal_time,
            exec_order.submission_time,
            used_ack_time,
            fill_time
        )
        latency_log = LatencyLog(
            execution_order_id=execution_order_id,
            signal_generation_time=exec_order.signal_time,
            order_submission_time=exec_order.submission_time,
            exchange_ack_time=used_ack_time,
            fill_time=fill_time,
            signal_to_submit_ms=latencies["signal_to_submit_ms"],
            submit_to_ack_ms=latencies["submit_to_ack_ms"],
            ack_to_fill_ms=latencies["ack_to_fill_ms"],
            total_execution_delay_ms=latencies["total_execution_delay_ms"],
        )
        self.db.add(latency_log)

        # Record Slippage logs
        slip_category = SlippageAnalyzer.categorize_slippage(slippage_pct)
        eq_settings = get_settings()
        slippage_log = SlippageLog(
            execution_order_id=execution_order_id,
            slippage_pct=Decimal(str(slippage_pct)),
            slippage_category=slip_category.value,
            volatility_rolling=Decimal(str(eq_settings.eq_default_volatility)),
            spread=Decimal(str(eq_settings.eq_default_spread)),
        )
        self.db.add(slippage_log)

        self.db.commit()
        
        # Recalculate metrics
        self.recalculate_metrics(exec_order.strategy_name)

        return fill

    def recalculate_metrics(self, strategy_name: str) -> ExecutionMetric:
        """
        Recalculates quality scores and outputs a new Metric entry.
        """
        # Fetch last 50 filled orders for this strategy
        orders = (
            self.db.query(ExecutionOrder)
            .filter(ExecutionOrder.strategy_name == strategy_name, ExecutionOrder.status.in_(["filled", "partially_filled"]))
            .order_by(ExecutionOrder.created_at.desc())
            .limit(50)
            .all()
        )

        if not orders:
            # Fallback default metric
            metric = ExecutionMetric(
                strategy_name=strategy_name,
                execution_quality_score=Decimal("100.0")
            )
            self.db.add(metric)
            self.db.commit()
            return metric

        order_ids = [o.id for o in orders]
        
        # Fills
        fills = self.db.query(ExecutionFill).filter(ExecutionFill.execution_order_id.in_(order_ids)).all()
        slippages = [float(f.slippage) for f in fills]
        
        # Latencies
        latency_records = self.db.query(LatencyLog).filter(LatencyLog.execution_order_id.in_(order_ids)).all()
        
        avg_slip = np.mean(slippages) if slippages else 0.0
        std_slip = np.std(slippages) if len(slippages) > 1 else 0.0

        avg_sig_sub = np.mean([rec.signal_to_submit_ms for rec in latency_records]) if latency_records else 0.0
        avg_sub_ack = np.mean([rec.submit_to_ack_ms for rec in latency_records]) if latency_records else 0.0
        avg_ack_fill = np.mean([rec.ack_to_fill_ms for rec in latency_records]) if latency_records else 0.0
        avg_total_lat = np.mean([rec.total_execution_delay_ms for rec in latency_records]) if latency_records else 0.0

        # Completion rates
        completion_rates = [
            FillAnalyzer.calculate_completion_rate(float(o.expected_quantity), float(sum(f.fill_quantity for f in fills if f.execution_order_id == o.id)))
            for o in orders
        ]
        avg_completion = np.mean(completion_rates) if completion_rates else 1.0
        
        partial_orders_count = sum(1 for o in orders if o.status == "partially_filled")
        partial_ratio = FillAnalyzer.calculate_partial_ratio(len(orders), partial_orders_count)

        # Computations of scores
        slippage_score = ExecutionMetricsCalculator.compute_slippage_score(avg_slip)
        latency_score = ExecutionMetricsCalculator.compute_latency_score(avg_total_lat)
        
        price_accuracy_score = slippage_score
        speed_score = latency_score
        fill_consistency = FillAnalyzer.calculate_fill_consistency(slippages)
        fill_quality = ExecutionMetricsCalculator.compute_fill_quality_score(
            price_accuracy_score,
            avg_completion,
            speed_score,
            fill_consistency
        )

        overall_score = ExecutionMetricsCalculator.compute_overall_quality_score(
            slippage_score,
            fill_quality,
            latency_score,
            fill_consistency
        )

        metric = ExecutionMetric(
            strategy_name=strategy_name,
            slippage_avg=Decimal(str(avg_slip)),
            slippage_std=Decimal(str(std_slip)),
            latency_signal_submit_ms=Decimal(str(avg_sig_sub)),
            latency_submit_ack_ms=Decimal(str(avg_sub_ack)),
            latency_ack_fill_ms=Decimal(str(avg_ack_fill)),
            latency_total_execution_ms=Decimal(str(avg_total_lat)),
            fill_completion_rate=Decimal(str(avg_completion)),
            partial_fill_ratio=Decimal(str(partial_ratio)),
            execution_quality_score=Decimal(str(overall_score))
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def detect_anomalies(self, strategy_name: str) -> Tuple[bool, str]:
        """
        Detects execution anomalies:
        - Latency spike (Z-score on total delay)
        - Slippage spike
        - Partial fill explosion
        """
        eq_settings = get_settings()
        # Fetch last 30 logs
        orders = (
            self.db.query(ExecutionOrder)
            .filter(ExecutionOrder.strategy_name == strategy_name, ExecutionOrder.status.in_(["filled", "partially_filled"]))
            .order_by(ExecutionOrder.created_at.desc())
            .limit(30)
            .all()
        )
        if len(orders) < 5:
            return False, "insufficient_data"

        order_ids = [o.id for o in orders]
        latency_records = self.db.query(LatencyLog).filter(LatencyLog.execution_order_id.in_(order_ids)).all()
        delays = [rec.total_execution_delay_ms for rec in latency_records]
        
        # 1. Latency Spike check
        mean_delay = np.mean(delays)
        std_delay = np.std(delays)
        if std_delay > 0:
            latest_delay = delays[0] if delays else 0
            z_lat = (latest_delay - mean_delay) / std_delay
            if z_lat > eq_settings.eq_latency_zscore_threshold:
                return True, f"latency_spike_detected (Z-score: {z_lat:.2f})"

        # 2. Critical Slippage check
        fills = self.db.query(ExecutionFill).filter(ExecutionFill.execution_order_id.in_(order_ids)).all()
        slippages = [abs(float(f.slippage)) for f in fills]
        
        if slippages:
            latest_slip = slippages[0]
            if latest_slip > eq_settings.eq_critical_slippage_pct:
                return True, f"critical_slippage_anomaly (slippage: {latest_slip * 100:.2f}%)"

        # 3. Partial fill explosion
        partial_fills = sum(1 for o in orders[:10] if o.status == "partially_filled")
        if partial_fills >= eq_settings.eq_partial_fill_explosion_threshold:
            return True, f"partial_fill_explosion ({partial_fills} partial fills in last 10 orders)"

        return False, "normal"

    def _window_candles(self, symbols, start_time, end_time) -> dict:
        """Fetch the window's candles per symbol once (shared by TCA benchmarks)."""
        timeframe = get_settings().market_data_interval
        out: dict[str, list] = {}
        for symbol in symbols:
            out[symbol] = (
                self.db.query(HistoricalCandle)
                .filter(
                    HistoricalCandle.symbol == symbol,
                    HistoricalCandle.timeframe == timeframe,
                    HistoricalCandle.timestamp >= start_time,
                    HistoricalCandle.timestamp <= end_time,
                )
                .order_by(HistoricalCandle.timestamp.asc())
                .all()
            )
        return out

    def _vwap_twap_benchmark(self, orders, fills, candles_by_symbol) -> dict:
        """Average fill execution vs the window VWAP/TWAP, per fill, in bps.

        Compares each fill price against its symbol's volume-weighted (VWAP) and
        time-weighted (TWAP) market price over the reporting window.
        """
        bench: dict[str, dict] = {}
        for symbol, candles in candles_by_symbol.items():
            if candles:
                closes = [float(c.close) for c in candles]
                volumes = [float(c.volume) for c in candles]
                bench[symbol] = {"vwap": vwap(closes, volumes), "twap": twap(closes)}

        order_by_id = {o.id: o for o in orders}
        vwap_bps, twap_bps = [], []
        for f in fills:
            order = order_by_id.get(f.execution_order_id)
            if order is None or order.symbol not in bench:
                continue
            ref = bench[order.symbol]
            if ref["vwap"] > 0:
                vwap_bps.append(benchmark_slippage_bps(order.side, float(f.fill_price), ref["vwap"]))
            if ref["twap"] > 0:
                twap_bps.append(benchmark_slippage_bps(order.side, float(f.fill_price), ref["twap"]))
        return {
            "avg_vwap_slippage_bps": sum(vwap_bps) / len(vwap_bps) if vwap_bps else 0.0,
            "avg_twap_slippage_bps": sum(twap_bps) / len(twap_bps) if twap_bps else 0.0,
            "fills_benchmarked": len(vwap_bps),
        }

    def _adverse_selection(self, orders, fills, candles_by_symbol, horizon_bars: int = 3) -> dict:
        """Post-fill markout: did the market move against fills shortly after?

        A persistently negative average markout (and a high adverse-fill ratio)
        signals adverse selection — fills land right before the price turns
        against the position (informed flow / lagging signals).
        """
        order_by_id = {o.id: o for o in orders}
        markouts = []
        for f in fills:
            order = order_by_id.get(f.execution_order_id)
            if order is None:
                continue
            candles = candles_by_symbol.get(order.symbol) or []
            # First candle at/after the fill, then look `horizon_bars` ahead.
            future = None
            for i, c in enumerate(candles):
                if c.timestamp >= f.fill_time:
                    nxt = candles[min(i + horizon_bars, len(candles) - 1)]
                    future = float(nxt.close)
                    break
            if future is not None:
                markouts.append(markout_bps(order.side, float(f.fill_price), future))
        if not markouts:
            return {"avg_markout_bps": 0.0, "adverse_fill_ratio": 0.0, "fills_analyzed": 0}
        adverse = sum(1 for m in markouts if m < 0)
        return {
            "avg_markout_bps": sum(markouts) / len(markouts),
            "adverse_fill_ratio": adverse / len(markouts),
            "fills_analyzed": len(markouts),
        }

    def generate_report(
        self,
        strategy_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> ExecutionReport:
        """
        Compiles the historical performance execution report.
        """
        orders = (
            self.db.query(ExecutionOrder)
            .filter(
                ExecutionOrder.strategy_name == strategy_name,
                ExecutionOrder.created_at.between(start_time, end_time),
                ExecutionOrder.status.in_(["filled", "partially_filled"])
            )
            .all()
        )

        if not orders:
            report = ExecutionReport(
                strategy_name=strategy_name,
                start_time=start_time,
                end_time=end_time,
                report_data={}
            )
            self.db.add(report)
            self.db.commit()
            return report

        order_ids = [o.id for o in orders]
        fills = self.db.query(ExecutionFill).filter(ExecutionFill.execution_order_id.in_(order_ids)).all()
        latency_records = self.db.query(LatencyLog).filter(LatencyLog.execution_order_id.in_(order_ids)).all()

        total_orders = len(orders)
        total_fills = len(fills)

        avg_slippage = np.mean([float(f.slippage) for f in fills]) if fills else 0.0
        avg_latency = np.mean([rec.total_execution_delay_ms for rec in latency_records]) if latency_records else 0.0

        # Quality Score mapping
        metrics_history = (
            self.db.query(ExecutionMetric)
            .filter(ExecutionMetric.strategy_name == strategy_name)
            .order_by(ExecutionMetric.timestamp.desc())
            .first()
        )
        avg_score = float(metrics_history.execution_quality_score) if metrics_history else 100.0

        # Calculate estimated slippage cost (USD)
        # Slippage Cost = Sum(abs(slippage) * filled_qty * fill_price)
        slippage_cost = Decimal("0")
        for f in fills:
            ord_ref = next((o for o in orders if o.id == f.execution_order_id), None)
            if ord_ref:
                cost = Decimal(str(abs(f.slippage))) * f.fill_quantity * f.fill_price
                slippage_cost += cost

        # Sharpe degradation estimation
        sharpe_deg = ExecutionBenchmarkSystem.estimate_sharpe_degradation(1.8, abs(avg_slippage), len(orders))

        # Recommendations list
        recs = AdaptiveExecutionOptimizer.generate_recommendations(
            avg_slippage,
            avg_latency,
            volatility=0.015,
            partial_fill_ratio=sum(1 for o in orders if o.status == "partially_filled") / total_orders
        )

        # Implementation shortfall (TCA) per order, against the decision price.
        is_records = []
        for f in fills:
            ord_ref = next((o for o in orders if o.id == f.execution_order_id), None)
            if ord_ref is None:
                continue
            is_records.append(
                implementation_shortfall(
                    side=ord_ref.side,
                    decision_price=float(ord_ref.expected_price),
                    fill_price=float(f.fill_price),
                    fill_quantity=float(f.fill_quantity),
                    expected_quantity=float(ord_ref.expected_quantity),
                    fee=float(f.fee),
                )
            )

        # Shared market-data fetch for the VWAP/TWAP and adverse-selection TCA.
        candles_by_symbol = self._window_candles({o.symbol for o in orders}, start_time, end_time)

        report_data = {
            "slippage_distribution": {
                "good": sum(1 for f in fills if abs(f.slippage) < 0.0005),
                "normal": sum(1 for f in fills if 0.0005 <= abs(f.slippage) <= 0.0020),
                "bad": sum(1 for f in fills if 0.0020 < abs(f.slippage) <= 0.0050),
                "critical": sum(1 for f in fills if abs(f.slippage) > 0.0050),
            },
            "implementation_shortfall": aggregate_implementation_shortfall(is_records),
            "execution_benchmark": self._vwap_twap_benchmark(orders, fills, candles_by_symbol),
            "adverse_selection": self._adverse_selection(orders, fills, candles_by_symbol),
            "recommendations": recs
        }

        report = ExecutionReport(
            strategy_name=strategy_name,
            start_time=start_time,
            end_time=end_time,
            total_orders=total_orders,
            total_fills=total_fills,
            average_slippage_pct=Decimal(str(avg_slippage)),
            average_latency_ms=Decimal(str(avg_latency)),
            average_quality_score=Decimal(str(avg_score)),
            sharpe_decay=Decimal(str(sharpe_deg)),
            slippage_cost_usd=slippage_cost,
            report_data=report_data,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report
