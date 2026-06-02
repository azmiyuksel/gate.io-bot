"""Multiple-testing / selection-bias assessment for parameter optimization.

Picking the single best configuration out of N backtests inflates its apparent
Sharpe: even random strategies produce a high "best" Sharpe when you try enough
of them. This implements the Bailey & López de Prado core idea — the expected
maximum Sharpe under the null given N trials — so a selected config can be
flagged when it is no better than chance.
"""
from __future__ import annotations

import math
from statistics import NormalDist, stdev

_EULER_MASCHERONI = 0.5772156649015329
_ND = NormalDist()


def expected_max_sharpe(n_trials: int, sharpe_std: float) -> float:
    """Expected maximum of `n_trials` Sharpe estimates under the null (true SR=0).

    Uses the extreme-value approximation E[max] ≈ σ_SR·[(1-γ)·Z⁻¹(1-1/N) +
    γ·Z⁻¹(1-1/(N·e))]. Inputs and output share the same (annualized) units.
    """
    if n_trials < 2 or sharpe_std <= 0:
        return 0.0
    z1 = _ND.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _ND.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return sharpe_std * ((1.0 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)


def assess_multiple_testing(trial_sharpes: list[float]) -> dict:
    """Assess whether the best Sharpe out of many trials is likely overfit.

    `likely_overfit` is True when the best observed Sharpe does not exceed the
    Sharpe you'd expect to see by chance as the maximum of this many trials.
    """
    n = len(trial_sharpes)
    if n == 0:
        return {
            "n_trials": 0,
            "sharpe_std": 0.0,
            "best_sharpe": 0.0,
            "expected_max_sharpe_under_null": 0.0,
            "deflation_gap": 0.0,
            "likely_overfit": False,
        }
    best = max(trial_sharpes)
    std = stdev(trial_sharpes) if n > 1 else 0.0
    exp_max = expected_max_sharpe(n, std)
    return {
        "n_trials": n,
        "sharpe_std": std,
        "best_sharpe": best,
        "expected_max_sharpe_under_null": exp_max,
        "deflation_gap": float(best - exp_max),
        "likely_overfit": bool(n > 1 and best <= exp_max),
    }
