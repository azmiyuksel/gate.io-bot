from decimal import Decimal
from typing import Dict, List, Any

from app.execution_quality.models import SlippageCategory


class SlippageAnalyzer:
    @staticmethod
    def calculate_slippage(side: str, expected_price: float, fill_price: float) -> float:
        """
        Calculates slippage percentage:
        - For buy order: slippage = (fill_price - expected_price) / expected_price
        - For sell order: slippage = (expected_price - fill_price) / expected_price
        Negative slippage means price improvement (good execution).
        """
        if expected_price <= 0:
            return 0.0
            
        diff = fill_price - expected_price
        if side.lower() == "buy":
            slippage = diff / expected_price
        else:
            slippage = -diff / expected_price
            
        return float(slippage)

    @staticmethod
    def categorize_slippage(slippage_pct: float) -> SlippageCategory:
        """
        Categorizes slippage into GOOD, NORMAL, BAD, or CRITICAL.
        """
        abs_slip = abs(slippage_pct)
        if abs_slip < 0.0005:
            return SlippageCategory.good
        elif abs_slip <= 0.0020:
            return SlippageCategory.normal
        elif abs_slip <= 0.0050:
            return SlippageCategory.bad
        else:
            return SlippageCategory.critical

    @staticmethod
    def calculate_volatility_multiplier(volatility: float) -> float:
        """
        Estimates the volatility-based slippage multiplier.
        """
        # If volatility is high, expected slippage increases.
        # Volatility is usually represented as standard dev of returns (e.g. 0.01 - 0.05 range).
        return float(1.0 + max(0.0, volatility * 100.0))
