"""Tests for stablecoin depeg detection."""
from decimal import Decimal

from app.services.risk.stablecoin import depeg_deviation, is_depegged


def test_depeg_deviation():
    assert depeg_deviation(Decimal("1.00")) == Decimal("0")
    assert depeg_deviation(Decimal("0.95")) == Decimal("0.05")


def test_is_depegged_threshold():
    # 1% threshold: 0.5% drift is fine, 2% drift is a depeg.
    assert is_depegged(Decimal("1.005"), 0.01) is False
    assert is_depegged(Decimal("0.98"), 0.01) is True
    assert is_depegged(Decimal("1.02"), 0.01) is True


def test_is_depegged_no_signal_does_not_alarm():
    assert is_depegged(None, 0.01) is False
    assert is_depegged(Decimal("0"), 0.01) is False
