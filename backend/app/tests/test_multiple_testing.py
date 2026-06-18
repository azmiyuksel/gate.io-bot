"""Tests for the multiple-testing / selection-bias assessment."""
from app.backtest.multiple_testing import assess_multiple_testing, expected_max_sharpe


def test_expected_max_sharpe_grows_with_trials():
    # More trials => higher expected maximum Sharpe purely by chance.
    few = expected_max_sharpe(5, sharpe_std=1.0)
    many = expected_max_sharpe(500, sharpe_std=1.0)
    assert 0 < few < many


def test_expected_max_sharpe_zero_for_single_trial():
    assert expected_max_sharpe(1, sharpe_std=1.0) == 0.0
    assert expected_max_sharpe(50, sharpe_std=0.0) == 0.0


def test_assess_flags_overfit_when_best_is_within_noise():
    # 200 trials of noisy Sharpes around 0: the best (~1.5) is what chance
    # produces, so it must be flagged as likely overfit.
    import numpy as np

    rng = np.random.default_rng(0)
    sharpes = [float(x) for x in rng.normal(0.0, 1.0, 200)]
    out = assess_multiple_testing(sharpes)
    assert out["n_trials"] == 200
    assert out["expected_max_sharpe_under_null"] > 0
    assert out["likely_overfit"] is True


def test_assess_does_not_flag_a_genuinely_strong_result():
    # One clearly dominant Sharpe far above the noisy crowd is not flagged.
    sharpes = [0.1, -0.2, 0.0, 0.3, -0.1, 8.0]
    out = assess_multiple_testing(sharpes)
    assert out["best_sharpe"] == 8.0
    assert out["likely_overfit"] is False
    assert out["deflation_gap"] > 0


def test_assess_empty():
    out = assess_multiple_testing([])
    assert out["n_trials"] == 0
    assert out["likely_overfit"] is False


# --- Deflated Sharpe Ratio (Bailey & López de Prado) ---


def test_dsr_pvalue_is_lower_for_a_stronger_sharpe():
    """A higher observed Sharpe (relative to the expected max under the null)
    must produce a LOWER p-value (more significant), not higher. The previous
    implementation returned Φ(z)^N which went UP with a higher z — backwards."""
    from app.strategy_research.backtest_runner import ResearchBacktestRunner
    from unittest.mock import MagicMock

    runner = ResearchBacktestRunner.__new__(ResearchBacktestRunner)
    runner.settings = MagicMock(
        research_population=100,
        research_min_trades=50,
        research_cv_purge_bars=200,
        research_cv_folds=5,
        research_wf_method="anchored",
    )
    # var_sharpe = 1/50 = 0.02 -> se ≈ 0.1414; 100 trials -> exp_max ~ 0.5-0.6.
    weak = runner._deflated_sharpe_ratio(0.3, n_trials=100, var_sharpe=0.02)
    strong = runner._deflated_sharpe_ratio(3.0, n_trials=100, var_sharpe=0.02)
    assert 0 <= weak <= 1 and 0 <= strong <= 1
    # The strong Sharpe (well above the expected max) is much less likely to be
    # a chance maximum -> lower p-value.
    assert strong < weak


def test_dsr_pvalue_high_when_observed_below_expected_max():
    """When the observed Sharpe is below the expected max under the null, the
    p-value must be high (likely spurious). The deflated Sharpe is negative."""
    from app.strategy_research.backtest_runner import ResearchBacktestRunner
    from unittest.mock import MagicMock

    runner = ResearchBacktestRunner.__new__(ResearchBacktestRunner)
    runner.settings = MagicMock(
        research_population=500,
        research_min_trades=50,
        research_cv_purge_bars=200,
        research_cv_folds=5,
        research_wf_method="anchored",
    )
    # 500 trials, se=0.14 -> expected max is high (~1.0+); a 0.2 Sharpe is
    # below that, so it's almost certainly a chance maximum.
    pvalue = runner._deflated_sharpe_ratio(0.2, n_trials=500, var_sharpe=0.02)
    assert pvalue > 0.5


def test_dsr_returns_one_for_zero_or_negative_sharpe():
    """No edge to deflate -> maximum spuriousness probability (1.0), not 0.0.
    The previous implementation returned 0.0 (false confidence in no-edge)."""
    from app.strategy_research.backtest_runner import ResearchBacktestRunner
    from unittest.mock import MagicMock

    runner = ResearchBacktestRunner.__new__(ResearchBacktestRunner)
    runner.settings = MagicMock(
        research_population=100,
        research_min_trades=50,
        research_cv_purge_bars=200,
        research_cv_folds=5,
        research_wf_method="anchored",
    )
    assert runner._deflated_sharpe_ratio(0.0) == 1.0
    assert runner._deflated_sharpe_ratio(-1.0) == 1.0
