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
