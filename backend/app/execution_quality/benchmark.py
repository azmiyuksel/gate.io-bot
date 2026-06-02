

class ExecutionBenchmarkSystem:
    @staticmethod
    def calculate_benchmark_slippage(
        side: str,
        ideal_price: float,
        actual_price: float
    ) -> float:
        """
        Calculates price deviation percentage from the ideal price benchmark:
        - Buy: (actual_price - ideal_price) / ideal_price
        - Sell: (ideal_price - actual_price) / ideal_price
        """
        if ideal_price <= 0:
            return 0.0
            
        diff = actual_price - ideal_price
        if side.lower() == "buy":
            return float(diff / ideal_price)
        else:
            return float(-diff / ideal_price)

    @staticmethod
    def estimate_sharpe_degradation(
        expected_sharpe: float,
        slippage_pct: float,
        trades_per_year: int = 250
    ) -> float:
        """
        Estimates the degradation of the strategy's Sharpe Ratio caused by slippage.
        Slippage costs act as a drag on returns, reducing the mean return while standard dev
        remains roughly constant.
        """
        # Estimate return drag (slippage_pct * trades_per_year)
        # Assuming an average standard deviation of returns of 15% (0.15)
        std_dev = 0.15
        return_drag = slippage_pct * trades_per_year
        degradation = return_drag / std_dev
        
        # Bounded to avoid clipping
        return float(min(expected_sharpe, max(0.0, degradation)))
