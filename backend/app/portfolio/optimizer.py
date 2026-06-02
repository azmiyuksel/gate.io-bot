from typing import Dict, List, Any


class PortfolioOptimizer:
    @staticmethod
    def optimize_strategy_weights(
        strategies: List[Dict[str, Any]], 
        correlation_matrix: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Optimizes weights for strategies based on Sharpe ratio, stability, and correlation penalties.
        """
        if not strategies:
            return {}

        raw_weights = {}
        total_score = 0.0

        for strat in strategies:
            name = strat["name"]
            sharpe = float(strat.get("sharpe_ratio", 0.0))
            drawdown = float(strat.get("max_drawdown", 0.0))
            stability = float(strat.get("stability_score", 0.5))

            # Base score = Sharpe + stability
            score = max(0.1, sharpe) + stability

            # Drawdown penalty
            if drawdown > 0.15:
                score *= 0.5
            elif drawdown > 0.05:
                score *= 0.8

            raw_weights[name] = score
            total_score += score

        if total_score <= 0:
            return {s["name"]: 1.0 / len(strategies) for s in strategies}

        # Normalize weights
        normalized = {name: score / total_score for name, score in raw_weights.items()}

        # Apply correlation penalty if applicable (for strategies executing on same/correlated symbols)
        for name1, weight1 in list(normalized.items()):
            penalty = 0.0
            for name2, weight2 in normalized.items():
                if name1 == name2:
                    continue
                # Simple correlation lookup (using defaults or placeholders if strategy correlations aren't tracked)
                corr = correlation_matrix.get(name1, {}).get(name2, 0.0)
                if corr > 0.8:
                    penalty += weight2 * 0.25  # Apply 25% penalty if highly correlated

            normalized[name1] = max(0.05, weight1 - penalty)

        # Re-normalize weights
        total_normalized = sum(normalized.values())
        if total_normalized > 0:
            normalized = {name: w / total_normalized for name, w in normalized.items()}

        return normalized
