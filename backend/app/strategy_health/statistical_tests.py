"""Statistical significance tests for strategy-health degradation.

These let the health engine distinguish a real, significant performance drop
from ordinary sampling noise, instead of relying purely on fixed heuristic
thresholds. Dependency-free (normal approximations via math.erfc).
"""
from __future__ import annotations

import math


def normal_cdf(z: float) -> float:
    """Standard normal CDF Phi(z)."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def binomial_winrate_pvalue(wins: int, n: int, baseline_rate: float) -> float:
    """One-sided p-value that the observed win rate is BELOW the baseline.

    H0: true win rate == baseline_rate. Returns P(observe this win rate or worse)
    under H0 using the normal approximation with a continuity correction. A small
    value (e.g. < 0.05) means the drop is unlikely to be noise.
    """
    if n <= 0:
        return 1.0
    observed = wins / n
    if observed >= baseline_rate or not 0.0 < baseline_rate < 1.0:
        return 1.0
    sd = math.sqrt(baseline_rate * (1.0 - baseline_rate) / n)
    if sd == 0:
        return 1.0
    # Continuity correction of half a trade.
    z = (observed + 0.5 / n - baseline_rate) / sd
    return normal_cdf(z)


def loss_streak_pvalue(streak: int, loss_rate: float) -> float:
    """Probability of `streak` consecutive losses under an i.i.d. loss rate."""
    if streak <= 0:
        return 1.0
    loss_rate = min(max(loss_rate, 0.0), 1.0)
    return loss_rate ** streak


def sharpe_standard_error(sharpe: float, n: int) -> float:
    """Approximate standard error of an estimated Sharpe ratio (Lo, 2002)."""
    if n <= 1:
        return float("inf")
    return math.sqrt((1.0 + 0.5 * sharpe * sharpe) / n)


def is_sharpe_significantly_below(
    live_sharpe: float, baseline_sharpe: float, n: int, z: float = 1.64
) -> bool:
    """True when live Sharpe is below baseline by more than z standard errors."""
    if n <= 1:
        return False
    se = sharpe_standard_error(baseline_sharpe, n)
    return (baseline_sharpe - live_sharpe) > z * se
