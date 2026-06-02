"""Tests for the mean-variance and risk-parity portfolio optimizers."""
from app.portfolio.optimizer import PortfolioOptimizer


def test_covariance_from_correlation():
    vols = {"A": 0.1, "B": 0.2}
    corr = {"A": {"A": 1.0, "B": 0.5}, "B": {"A": 0.5, "B": 1.0}}
    cov = PortfolioOptimizer.covariance_from_correlation(vols, corr)
    assert abs(cov["A"]["A"] - 0.01) < 1e-12  # σ_A²
    assert abs(cov["B"]["B"] - 0.04) < 1e-12  # σ_B²
    assert abs(cov["A"]["B"] - 0.5 * 0.1 * 0.2) < 1e-12  # ρ·σ_A·σ_B


def test_mean_variance_max_sharpe_weights():
    # Uncorrelated assets, equal expected return: w ∝ Σ⁻¹μ ∝ (1/σ²).
    # σ²=(0.01, 0.04), μ=(0.1, 0.1) -> raw (10, 2.5) -> (0.8, 0.2).
    mu = {"A": 0.1, "B": 0.1}
    cov = {"A": {"A": 0.01, "B": 0.0}, "B": {"A": 0.0, "B": 0.04}}
    w = PortfolioOptimizer.mean_variance_weights(mu, cov)
    assert abs(w["A"] - 0.8) < 1e-6
    assert abs(w["B"] - 0.2) < 1e-6


def test_mean_variance_is_long_only():
    # A negative expected return would imply a short; long-only clips it to 0.
    mu = {"A": 0.2, "B": -0.1}
    cov = {"A": {"A": 0.04, "B": 0.0}, "B": {"A": 0.0, "B": 0.04}}
    w = PortfolioOptimizer.mean_variance_weights(mu, cov, long_only=True)
    assert w["A"] == 1.0
    assert w["B"] == 0.0


def test_risk_parity_uncorrelated_is_inverse_vol():
    # Uncorrelated: equal risk contribution => w ∝ 1/σ.
    # σ=(0.1, 0.2) -> w ∝ (10, 5) -> (2/3, 1/3).
    cov = {"A": {"A": 0.01, "B": 0.0}, "B": {"A": 0.0, "B": 0.04}}
    w = PortfolioOptimizer.risk_parity_weights(cov)
    assert abs(w["A"] - 2 / 3) < 1e-3
    assert abs(w["B"] - 1 / 3) < 1e-3


def test_risk_parity_equalizes_risk_contributions():
    import numpy as np

    cov = {
        "A": {"A": 0.04, "B": 0.006, "C": 0.0},
        "B": {"A": 0.006, "B": 0.09, "C": 0.01},
        "C": {"A": 0.0, "C": 0.0225, "B": 0.01},
    }
    symbols = ["A", "B", "C"]
    w = PortfolioOptimizer.risk_parity_weights(cov)
    vec = np.array([w[s] for s in symbols])
    sigma = np.array([[cov[a].get(b, 0.0) for b in symbols] for a in symbols])
    rc = vec * (sigma @ vec)
    # All risk contributions should be (approximately) equal.
    assert rc.std() / rc.mean() < 0.02
    assert abs(sum(w.values()) - 1.0) < 1e-9
