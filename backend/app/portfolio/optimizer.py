from typing import Dict, List, Any

import numpy as np


def _matrix(symbols: list[str], cov: Dict[str, Dict[str, float]]) -> np.ndarray:
    return np.array(
        [[float(cov.get(a, {}).get(b, 0.0)) for b in symbols] for a in symbols],
        dtype="float64",
    )


class PortfolioOptimizer:
    @staticmethod
    def covariance_from_correlation(
        volatilities: Dict[str, float], correlation: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """Build a covariance matrix from per-asset volatility and correlation:
        Σ_ij = ρ_ij · σ_i · σ_j."""
        symbols = list(volatilities.keys())
        cov: Dict[str, Dict[str, float]] = {}
        for a in symbols:
            cov[a] = {}
            for b in symbols:
                rho = 1.0 if a == b else float(correlation.get(a, {}).get(b, 0.0))
                cov[a][b] = rho * float(volatilities[a]) * float(volatilities[b])
        return cov

    @staticmethod
    def mean_variance_weights(
        expected_returns: Dict[str, float],
        covariance: Dict[str, Dict[str, float]],
        long_only: bool = True,
    ) -> Dict[str, float]:
        """Markowitz max-Sharpe (tangency) weights: w ∝ Σ⁻¹ μ.

        Long-only by default (negative weights clipped, then renormalized), which
        is the standard practical approximation for a spot, no-short portfolio.
        """
        symbols = list(expected_returns.keys())
        if not symbols:
            return {}
        if len(symbols) == 1:
            return {symbols[0]: 1.0}
        mu = np.array([float(expected_returns[s]) for s in symbols], dtype="float64")
        sigma = _matrix(symbols, covariance)
        # Pseudo-inverse for numerical robustness against singular matrices.
        raw = np.linalg.pinv(sigma) @ mu
        if long_only:
            raw = np.clip(raw, 0.0, None)
        total = raw.sum()
        if total <= 0:
            return {s: 1.0 / len(symbols) for s in symbols}
        weights = raw / total
        return {s: float(w) for s, w in zip(symbols, weights)}

    @staticmethod
    def risk_parity_weights(
        covariance: Dict[str, Dict[str, float]], iterations: int = 200
    ) -> Dict[str, float]:
        """Long-only risk parity: each asset contributes equal portfolio risk.

        Solved with a damped multiplicative fixed-point iteration (no SciPy):
        start from inverse-volatility weights and nudge weight toward assets whose
        risk contribution is below the average until contributions equalise.
        """
        symbols = list(covariance.keys())
        if not symbols:
            return {}
        if len(symbols) == 1:
            return {symbols[0]: 1.0}
        sigma = _matrix(symbols, covariance)
        variances = np.clip(np.diag(sigma), 1e-12, None)
        w = 1.0 / np.sqrt(variances)  # inverse-vol start
        w /= w.sum()
        for _ in range(iterations):
            mrc = sigma @ w  # marginal risk contributions
            rc = w * mrc  # risk contribution per asset
            target = rc.mean()
            if target <= 0:
                break
            # Damped update (sqrt) toward equal risk contribution.
            w = w * np.sqrt(target / np.clip(rc, 1e-18, None))
            w = np.clip(w, 1e-12, None)
            w /= w.sum()
        return {s: float(weight) for s, weight in zip(symbols, w)}

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
