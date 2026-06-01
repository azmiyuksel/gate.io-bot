from app.models.enums import MarketRegimeType


class VolatilityClassifier:
    @staticmethod
    def classify_volatility(row: dict, historical_mean_bbw: float = 0.05) -> MarketRegimeType:
        """
        Classifies volatility states (HIGH_VOLATILITY, LOW_VOLATILITY, or BREAKOUT_PHASE).
        """
        bb_width = row.get("bb_width", 0.0)
        realized_vol = row.get("realized_vol", 0.0)
        close = row.get("close", 0.0)
        open_price = row.get("open", 0.0)
        
        # Thresholds
        high_vol_thresh = historical_mean_bbw * 2.0
        low_vol_thresh = historical_mean_bbw * 0.5

        # Check for rapid volatility expansion (breakout)
        price_body_pct = abs(close - open_price) / open_price if open_price > 0 else 0.0
        
        if bb_width > high_vol_thresh or realized_vol > 0.40:
            return MarketRegimeType.high_volatility
        elif bb_width < low_vol_thresh:
            return MarketRegimeType.low_volatility
        elif bb_width > historical_mean_bbw * 1.3 and price_body_pct > 0.02:
            # Volatility is expanding, large price change -> breakout phase
            return MarketRegimeType.breakout_phase
            
        return MarketRegimeType.sideways
