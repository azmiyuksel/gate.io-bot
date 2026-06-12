from app.models.enums import MarketRegimeType


class TrendClassifier:
    @staticmethod
    def classify_trend(row: dict) -> MarketRegimeType:
        """
        Classifies the trend regime for a single feature row.

        Uses ADX thresholds of 20/25 to distinguish trending from sideways:
            - ADX > 25: strong trend — classify as bull or bear
            - ADX 20–25: weak trend — classify based on MA/slope alignment
            - ADX < 20: no trend — sideways
        """
        close = row.get("close", 0.0)
        ema_20 = row.get("ema_20", 0.0)
        ema_50 = row.get("ema_50", 0.0)
        ema_200 = row.get("ema_200", 0.0)
        ema_200_slope = row.get("ema_200_slope", 0.0)
        adx = row.get("adx", 0.0)

        # Bull conditions: Price above EMA 200, short EMAs stacked positively
        is_bull_ma = (close > ema_200) and (ema_20 > ema_50 > ema_200)
        is_bull_slope = ema_200_slope > 0.0005

        # Bear conditions: Price below EMA 200, short EMAs stacked negatively
        is_bear_ma = (close < ema_200) and (ema_20 < ema_50 < ema_200)
        is_bear_slope = ema_200_slope < -0.0005

        if adx > 25:
            # Strong trend: classify by MA/slope alignment
            if is_bull_ma or is_bull_slope:
                return MarketRegimeType.trending_bull
            elif is_bear_ma or is_bear_slope:
                return MarketRegimeType.trending_bear
            # ADX > 25 but no clear direction (choppy trend) — default to sideways
            return MarketRegimeType.sideways
        elif adx > 20:
            # Weak trend: require MA alignment to confirm
            if is_bull_ma:
                return MarketRegimeType.trending_bull
            elif is_bear_ma:
                return MarketRegimeType.trending_bear

        return MarketRegimeType.sideways
