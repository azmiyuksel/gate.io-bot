from datetime import datetime, timedelta, UTC
import pytest

from app.execution_quality.models import SlippageCategory
from app.execution_quality.slippage_analyzer import SlippageAnalyzer
from app.execution_quality.fill_analyzer import FillAnalyzer
from app.execution_quality.latency_tracker import LatencyTracker
from app.execution_quality.order_book_simulator import OrderBookSimulator
from app.execution_quality.metrics import ExecutionMetricsCalculator
from app.execution_quality.optimizer import AdaptiveExecutionOptimizer


def test_slippage_calculation_and_categorization() -> None:
    # 1. Buy order slippage
    buy_slip = SlippageAnalyzer.calculate_slippage("buy", 100.0, 100.2)
    assert buy_slip == pytest.approx(0.002)  # +0.2% slippage (worse price)

    # 2. Sell order slippage
    sell_slip = SlippageAnalyzer.calculate_slippage("sell", 100.0, 99.8)
    assert sell_slip == pytest.approx(0.002)  # +0.2% slippage (worse price)

    # 3. Price improvement
    improvement = SlippageAnalyzer.calculate_slippage("buy", 100.0, 99.9)
    assert improvement == pytest.approx(-0.001)  # -0.1% slippage (better price)

    # 4. Categorization
    assert SlippageAnalyzer.categorize_slippage(0.0003) == SlippageCategory.good
    assert SlippageAnalyzer.categorize_slippage(0.0015) == SlippageCategory.normal
    assert SlippageAnalyzer.categorize_slippage(0.0035) == SlippageCategory.bad
    assert SlippageAnalyzer.categorize_slippage(0.0065) == SlippageCategory.critical


def test_fill_and_latency_tracking() -> None:
    # 1. Completion Rate
    assert FillAnalyzer.calculate_completion_rate(100.0, 100.0) == 1.0
    assert FillAnalyzer.calculate_completion_rate(100.0, 50.0) == 0.5
    assert FillAnalyzer.calculate_completion_rate(100.0, 0.0) == 0.0

    # 2. Partial Ratio
    assert FillAnalyzer.calculate_partial_ratio(10, 3) == 0.3

    # 3. Consistency calculation
    cons = FillAnalyzer.calculate_fill_consistency([0.001, 0.001, 0.001])
    assert cons == 100.0  # Zero standard deviation

    # 4. Latency tracker
    t_sig = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    t_sub = t_sig + timedelta(milliseconds=100)
    t_ack = t_sub + timedelta(milliseconds=200)
    t_fill = t_ack + timedelta(milliseconds=300)

    lats = LatencyTracker.calculate_latencies(t_sig, t_sub, t_ack, t_fill)
    assert lats["signal_to_submit_ms"] == 100
    assert lats["submit_to_ack_ms"] == 200
    assert lats["ack_to_fill_ms"] == 300
    assert lats["total_execution_delay_ms"] == 600


def test_order_book_simulator_impact() -> None:
    # Estimate market impact for a small order (should be minimal, basically half spread)
    small_impact = OrderBookSimulator.estimate_market_impact(
        order_quantity=1.0,
        mid_price=100.0,
        rolling_volume_24h=1_000_000.0,
        bid_ask_spread=0.0002,
        volatility=0.02
    )
    # Estimate impact for a huge order (should be significantly larger)
    large_impact = OrderBookSimulator.estimate_market_impact(
        order_quantity=50_000.0,
        mid_price=100.0,
        rolling_volume_24h=1_000_000.0,
        bid_ask_spread=0.0002,
        volatility=0.02
    )
    assert large_impact > small_impact
    assert small_impact == pytest.approx(0.0001 + 0.5 * 0.02 * (1.0 / 1_000_000.0) ** 0.5)


def test_execution_metrics_scoring() -> None:
    # 1. Slippage score mapping
    assert ExecutionMetricsCalculator.compute_slippage_score(0.0003) == 100.0
    assert ExecutionMetricsCalculator.compute_slippage_score(0.0015) == pytest.approx(83.33, abs=0.05)
    assert ExecutionMetricsCalculator.compute_slippage_score(0.0200) == 0.0

    # 2. Latency score mapping
    assert ExecutionMetricsCalculator.compute_latency_score(100) == 100.0
    assert ExecutionMetricsCalculator.compute_latency_score(1500) == pytest.approx(53.33, abs=0.05)

    # 3. Overall quality score
    overall = ExecutionMetricsCalculator.compute_overall_quality_score(
        slippage_score=95.0,
        fill_quality_score=90.0,
        latency_score=85.0,
        consistency_score=98.0
    )
    # Weighted: 0.40 * 95 + 0.30 * 90 + 0.20 * 85 + 0.10 * 98 = 38 + 27 + 17 + 9.8 = 91.8
    assert overall == pytest.approx(91.8)

    # 4. Efficiency score
    eff = ExecutionMetricsCalculator.calculate_efficiency_score(1000.0, 950.0)
    assert eff == 95.0



def test_adaptive_optimizer_recs() -> None:
    # 1. Low slippage, low latency (healthy)
    recs_healthy = AdaptiveExecutionOptimizer.generate_recommendations(0.0002, 100.0, 0.01, 0.0)
    assert len(recs_healthy) == 1
    assert recs_healthy[0]["type"] == "SYSTEM_HEALTHY"

    # 2. High slippage & latency
    recs_poor = AdaptiveExecutionOptimizer.generate_recommendations(0.0035, 2500.0, 0.04, 0.4)
    types = [r["type"] for r in recs_poor]
    assert "ORDER_TYPE_OPTIMIZATION" in types
    assert "LATENCY_OPTIMIZATION" in types
    assert "RISK_OPTIMIZATION" in types
    assert "LIQUIDITY_OPTIMIZATION" in types
