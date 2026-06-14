from decimal import Decimal
from typing import Dict, List, Any

from app.core.config import get_settings


class CapitalAllocator:
    @staticmethod
    def calculate_allocation_score(
        strategy_score: Decimal,
        risk_adjusted_return: Decimal,
        inverse_correlation_penalty: Decimal,
        stability_score: Decimal
    ) -> Decimal:
        """
        Calculates the allocation score using configurable weighted formula.
        """
        s = get_settings()
        score = (
            Decimal(str(s.alloc_weight_strategy)) * strategy_score +
            Decimal(str(s.alloc_weight_risk_adj)) * risk_adjusted_return +
            Decimal(str(s.alloc_weight_correlation)) * inverse_correlation_penalty +
            Decimal(str(s.alloc_weight_stability)) * stability_score
        )
        return max(Decimal("0.0"), score)

    def allocate_capital(
        self,
        total_equity: Decimal,
        strategies: List[Dict[str, Any]],
        strategy_correlations: Dict[str, float],
        drawdowns: Dict[str, Decimal]
    ) -> Dict[str, Decimal]:
        """
        Calculates the capital allocation (in USD) for each strategy based on scores and drawdowns.

        ``strategy_correlations`` maps strategy names to their average pairwise
        asset correlation (pre-computed by the engine from real trade symbols).
        """
        if total_equity <= 0 or not strategies:
            return {}

        allocation_scores = {}
        total_score = Decimal("0.0")

        for strat in strategies:
            name = strat["name"]
            
            # Extract inputs
            sharpe = Decimal(str(strat.get("sharpe_ratio", 0.0)))
            win_rate = Decimal(str(strat.get("win_rate", 0.0)))
            profit_factor = Decimal(str(strat.get("profit_factor", 1.0)))
            stability = Decimal(str(strat.get("stability_score", 0.5)))
            
            # 1. Strategy Score (normalized Sharpe + win rate + profit factor composite)
            # Sharpe: [0, 3] -> normalizes to [0, 1]
            sharpe_score = min(Decimal("1.0"), max(Decimal("0.0"), sharpe / Decimal("3.0")))
            strategy_score = Decimal("0.5") * sharpe_score + Decimal("0.3") * win_rate + Decimal("0.2") * min(Decimal("1.0"), profit_factor / Decimal("3.0"))
            
            # 2. Risk Adjusted Return
            risk_adjusted_return = min(Decimal("1.0"), max(Decimal("0.0"), sharpe / Decimal("2.0")))

            # 3. Inverse Correlation Penalty — uses per-strategy average asset correlation
            avg_corr = strategy_correlations.get(name, 0.5)
            inverse_correlation_penalty = Decimal(str(max(0.0, 1.0 - max(0.0, avg_corr))))

            # 4. Stability Score
            stability_score = stability

            # Compute score
            score = self.calculate_allocation_score(
                strategy_score,
                risk_adjusted_return,
                inverse_correlation_penalty,
                stability_score
            )

            # Drawdown Adjustment: high drawdown -> scale down allocation
            s = get_settings()
            dd = drawdowns.get(name, Decimal("0.0"))
            if dd > Decimal(str(s.alloc_dd_tier_high)):
                score *= Decimal(str(s.alloc_dd_scale_high))
            elif dd > Decimal(str(s.alloc_dd_tier_mid)):
                score *= Decimal(str(s.alloc_dd_scale_mid))
            elif dd > Decimal(str(s.alloc_dd_tier_low)):
                score *= Decimal(str(s.alloc_dd_scale_low))

            allocation_scores[name] = score
            total_score += score

        if total_score <= 0:
            # Fallback to equal weights
            equal_share = total_equity / Decimal(len(strategies))
            return {s["name"]: equal_share for s in strategies}

        # Distribute capital based on normalized scores
        allocations = {}
        for name, score in allocation_scores.items():
            allocations[name] = (score / total_score) * total_equity

        return allocations
