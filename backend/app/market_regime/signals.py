from decimal import Decimal
from typing import Tuple
from app.models.enums import MarketRegimeType
from app.market_regime.models import RISK_MULTIPLIERS


class RegimeSignalFilter:
    @staticmethod
    def get_risk_multiplier(regime: MarketRegimeType) -> Decimal:
        """
        Returns the risk multiplier based on current regime type.
        """
        return RISK_MULTIPLIERS.get(regime, Decimal("1.0"))

    @staticmethod
    def should_allow_trade(
        strategy_name: str,
        regime: MarketRegimeType,
        confidence: float
    ) -> Tuple[bool, str, Decimal]:
        """
        Evaluates trade filter rules based on strategy, current regime, and confidence.
        Returns: (allowed, reason, risk_multiplier_modifier)
        """
        # 1. Check Confidence System limits
        if confidence < 0.5:
            return False, "low_confidence_block", Decimal("0")
        
        # Determine confidence multiplier
        conf_mult = Decimal("1.0")
        if 0.5 <= confidence <= 0.7:
            # reduced risk
            conf_mult = Decimal("0.5")  # Cut risk in half for low confidence

        # Normalized strategy name to check rules
        strategy_name_lower = strategy_name.lower()

        # 2. Regime-specific Trade Rules
        if regime == MarketRegimeType.trending_bull:
            if "mean_reversion" in strategy_name_lower or "reversion" in strategy_name_lower:
                return False, "mean_reversion_disabled_in_bull_trend", Decimal("0")
            
        elif regime == MarketRegimeType.trending_bear:
            # Short-only or hedge mode (in standard platform, block long strategies)
            if "long" in strategy_name_lower or "bull" in strategy_name_lower:
                return False, "long_strategy_blocked_in_bear_trend", Decimal("0")

        elif regime == MarketRegimeType.sideways:
            if "breakout" in strategy_name_lower or "trend_following" in strategy_name_lower:
                return False, "breakout_and_trend_disabled_in_range", Decimal("0")

        elif regime == MarketRegimeType.high_volatility:
            # High volatility: cut risk by half, allow trend following
            conf_mult *= Decimal("0.5")
            if "reversion" in strategy_name_lower:
                return False, "mean_reversion_blocked_in_high_vol", Decimal("0")

        elif regime == MarketRegimeType.low_volatility:
            # Low volatility: allow breakouts (consolidation period)
            pass

        elif regime == MarketRegimeType.breakout_phase:
            # Breakout phase: allow breakouts, block mean reversion
            if "reversion" in strategy_name_lower:
                return False, "mean_reversion_blocked_in_breakout", Decimal("0")

        base_multiplier = RegimeSignalFilter.get_risk_multiplier(regime)
        final_multiplier = base_multiplier * conf_mult

        return True, "allowed", final_multiplier
