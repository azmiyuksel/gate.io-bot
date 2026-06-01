from typing import List, Dict, Any


class FillAnalyzer:
    @staticmethod
    def calculate_completion_rate(requested_qty: float, filled_qty: float) -> float:
        """
        Calculates the completion rate: filled_qty / requested_qty (0.0 to 1.0).
        """
        if requested_qty <= 0:
            return 0.0
        return float(min(1.0, max(0.0, filled_qty / requested_qty)))

    @staticmethod
    def calculate_partial_ratio(total_orders: int, partial_orders: int) -> float:
        """
        Calculates the partial fill ratio: partial_orders / total_orders.
        """
        if total_orders <= 0:
            return 0.0
        return float(min(1.0, max(0.0, partial_orders / total_orders)))

    @staticmethod
    def calculate_fill_consistency(slippage_history: List[float]) -> float:
        """
        Computes the consistency score based on standard deviation of slippages.
        Lower variance means higher consistency (returns 0-100).
        """
        if len(slippage_history) < 2:
            return 100.0
            
        mean = sum(slippage_history) / len(slippage_history)
        variance = sum((x - mean) ** 2 for x in slippage_history) / (len(slippage_history) - 1)
        std_dev = variance ** 0.5
        
        # Scale standard dev (e.g. std dev of 0.001 is very consistent, std dev of 0.02 is inconsistent)
        # Score = 100 - (std_dev * 5000), bounded between 0 and 100
        score = 100.0 - (std_dev * 5000.0)
        return float(max(0.0, min(100.0, score)))
