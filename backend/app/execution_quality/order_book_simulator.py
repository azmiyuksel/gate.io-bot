class OrderBookSimulator:
    @staticmethod
    def estimate_market_impact(
        order_quantity: float,
        mid_price: float,
        rolling_volume_24h: float,
        bid_ask_spread: float = 0.0002,
        volatility: float = 0.015
    ) -> float:
        """
        Estimates the expected slippage due to order size (liquidity impact) using
        a standard square-root market impact model:
        Slippage = (Half Spread) + Y * Volatility * sqrt(Order Quantity / Daily Volume)
        where Y is typically a scaling factor (e.g. 0.5).
        """
        if rolling_volume_24h <= 0 or order_quantity <= 0 or mid_price <= 0:
            return float(bid_ask_spread / 2.0)

        # Ratio of order size vs daily volume
        volume_ratio = order_quantity / rolling_volume_24h
        
        # Market impact scaling factor
        scaling_factor = 0.5
        
        # Estimate percentage impact
        impact = (bid_ask_spread / 2.0) + scaling_factor * volatility * (volume_ratio ** 0.5)
        
        return float(impact)

    @staticmethod
    def estimate_liquidity_depth(rolling_volume_24h: float, price: float) -> float:
        """
        Helper to estimate top-of-book/liquidity depth (USD value) as 1.5% of daily volume.
        """
        return max(1000.0, rolling_volume_24h * price * 0.015)
