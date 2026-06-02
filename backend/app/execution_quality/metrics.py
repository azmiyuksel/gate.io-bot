
from app.execution_quality.models import (
    SLIPPAGE_WEIGHT,
    FILL_QUALITY_WEIGHT,
    LATENCY_WEIGHT,
    CONSISTENCY_WEIGHT,
    FILL_PRICE_ACCURACY_WEIGHT,
    FILL_COMPLETION_WEIGHT,
    FILL_SPEED_WEIGHT,
    FILL_CONSISTENCY_WEIGHT,
)


class ExecutionMetricsCalculator:
    @staticmethod
    def compute_slippage_score(avg_slippage: float) -> float:
        """
        Maps average absolute slippage percentage to a 0-100 score:
        - <= 0.05% (0.0005) -> 100
        - 0.05% to 0.2% -> 100 to 75
        - 0.2% to 0.5% -> 75 to 50
        - > 0.5% -> decays linearly to 0 at 2.0% slippage
        """
        abs_slip = abs(avg_slippage)
        if abs_slip <= 0.0005:
            return 100.0
        elif abs_slip <= 0.0020:
            return 100.0 - ((abs_slip - 0.0005) / 0.0015) * 25.0
        elif abs_slip <= 0.0050:
            return 75.0 - ((abs_slip - 0.0020) / 0.0030) * 25.0
        else:
            return max(0.0, 50.0 - ((abs_slip - 0.0050) / 0.0150) * 50.0)

    @staticmethod
    def compute_latency_score(avg_total_latency_ms: float) -> float:
        """
        Maps total latency in milliseconds to a 0-100 score:
        - <= 150ms -> 100
        - 150ms to 500ms -> 100 to 80
        - 500ms to 2000ms -> 80 to 40
        - > 2000ms -> decays to 0 at 5000ms
        """
        lat = max(0.0, avg_total_latency_ms)
        if lat <= 150.0:
            return 100.0
        elif lat <= 500.0:
            return 100.0 - ((lat - 150.0) / 350.0) * 20.0
        elif lat <= 2000.0:
            return 80.0 - ((lat - 500.0) / 1500.0) * 40.0
        else:
            return max(0.0, 40.0 - ((lat - 2000.0) / 3000.0) * 40.0)

    @staticmethod
    def compute_fill_quality_score(
        price_accuracy_score: float,
        completion_rate: float,
        speed_score: float,
        consistency_score: float
    ) -> float:
        """
        Weighted average of fill quality sub-scores.
        """
        return (
            FILL_PRICE_ACCURACY_WEIGHT * price_accuracy_score +
            FILL_COMPLETION_WEIGHT * (completion_rate * 100.0) +
            FILL_SPEED_WEIGHT * speed_score +
            FILL_CONSISTENCY_WEIGHT * consistency_score
        )

    @staticmethod
    def compute_overall_quality_score(
        slippage_score: float,
        fill_quality_score: float,
        latency_score: float,
        consistency_score: float
    ) -> float:
        """
        Calculates final execution quality score (0-100).
        """
        score = (
            SLIPPAGE_WEIGHT * slippage_score +
            FILL_QUALITY_WEIGHT * fill_quality_score +
            LATENCY_WEIGHT * latency_score +
            CONSISTENCY_WEIGHT * consistency_score
        )
        return float(max(0.0, min(100.0, score)))

    @staticmethod
    def calculate_efficiency_score(ideal_profit: float, actual_profit: float) -> float:
        """
        Calculates execution efficiency: ideal_profit / actual_profit_loss_adjusted.
        Handles zero/negative balances.
        """
        if actual_profit == ideal_profit:
            return 100.0
        if actual_profit <= 0:
            # If actual is loss and ideal was gain/lower loss, efficiency is low
            if ideal_profit > 0:
                return 0.0
            # If both are losses, compare them
            if ideal_profit < 0:
                # If ideal loss was smaller (e.g. -50 vs -100), efficiency = 50%
                return float(max(0.0, min(100.0, (ideal_profit / actual_profit) * 100.0)))
            return 0.0
        
        # Both are positive
        if ideal_profit > 0:
            # If actual profit is larger than ideal, efficiency is > 100 (possible with positive slippage)
            return float(max(0.0, min(150.0, (actual_profit / ideal_profit) * 100.0)))
        return 0.0
