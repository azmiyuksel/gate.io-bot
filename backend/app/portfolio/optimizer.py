from typing import Dict, List, Any

import numpy as np


def _matrix(symbols: list[str], cov: Dict[str, Dict[str, float]]) -> np.ndarray:
    return np.array(
        [[float(cov.get(a, {}).get(b, 0.0)) for b in symbols] for a in symbols],
        dtype="float64",
    )


def _nearest_psd(sigma: np.ndarray, floor: float = 1e-12) -> np.ndarray:
    """Project a (possibly non-PSD) covariance matrix onto the nearest PSD matrix
    by clipping negative eigenvalues. No-op when the matrix is already PSD, so
    well-formed inputs are returned unchanged. Pairwise-estimated or fill-padded
    covariance matrices are frequently non-PSD, which makes inversion/risk-parity
    produce nonsense; this guards against that."""
    sym = (sigma + sigma.T) / 2.0
    try:
        eigvals, eigvecs = np.linalg.eigh(sym)
    except np.linalg.LinAlgError:
        return sym
    if eigvals.min() >= 0:
        return sym
    clipped = np.clip(eigvals, floor, None)
    repaired = (eigvecs * clipped) @ eigvecs.T
    return (repaired + repaired.T) / 2.0


def _shrink_covariance(sigma: np.ndarray, intensity: float) -> np.ndarray:
    """Ledoit-Wolf-style shrinkage toward a diagonal target (shrink correlations
    toward zero). intensity in [0, 1]; 0 = raw sample covariance. Reduces the
    estimation error that the Markowitz optimizer otherwise maximizes."""
    if intensity <= 0:
        return sigma
    intensity = min(intensity, 1.0)
    target = np.diag(np.diag(sigma))
    return (1.0 - intensity) * sigma + intensity * target


def _cap_weights(weights: np.ndarray, max_weight: float, iterations: int = 50) -> np.ndarray:
    """Cap each weight at max_weight and redistribute the excess to uncapped
    names, preserving the sum. Prevents single-asset concentration."""
    w = weights.copy()
    n = len(w)
    if max_weight <= 0 or max_weight >= 1 or n == 0 or 1.0 / n > max_weight:
        return w
    for _ in range(iterations):
        over = w > max_weight + 1e-12
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        free = ~over
        if not free.any():
            break
        w[free] += excess * (w[free] / w[free].sum())
    return w


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
        shrinkage: float = 0.0,
        ridge: float = 0.0,
        max_weight: float | None = None,
    ) -> Dict[str, float]:
        """Markowitz max-Sharpe (tangency) weights: w ∝ Σ⁻¹ μ.

        Long-only by default (negative weights clipped, then renormalized), which
        is the standard practical approximation for a spot, no-short portfolio.

        Robustness controls (all default to a no-op so the raw Markowitz solution
        is preserved unless requested):
          - ``shrinkage`` (0..1): Ledoit-Wolf-style shrinkage of Σ toward its
            diagonal, taming the estimation error Markowitz amplifies.
          - ``ridge``: add ``ridge`` to the diagonal of Σ for invertibility.
          - ``max_weight``: per-asset weight cap to avoid concentration.
        The covariance is always projected to the nearest PSD matrix first (a
        no-op when already PSD) to avoid garbage from non-PSD inputs.
        """
        symbols = list(expected_returns.keys())
        if not symbols:
            return {}
        if len(symbols) == 1:
            return {symbols[0]: 1.0}
        mu = np.array([float(expected_returns[s]) for s in symbols], dtype="float64")
        sigma = _nearest_psd(_matrix(symbols, covariance))
        sigma = _shrink_covariance(sigma, shrinkage)
        if ridge > 0:
            sigma = sigma + ridge * np.eye(len(symbols))
        # Pseudo-inverse for numerical robustness against singular matrices.
        raw = np.linalg.pinv(sigma) @ mu
        if long_only:
            raw = np.clip(raw, 0.0, None)
        total = raw.sum()
        if total <= 0:
            return {s: 1.0 / len(symbols) for s in symbols}
        weights = raw / total
        if max_weight is not None:
            weights = _cap_weights(weights, max_weight)
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
        sigma = _nearest_psd(_matrix(symbols, covariance))
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
