"""Stablecoin depeg monitoring.

The entire account is denominated in the quote stablecoin (USDT), so a depeg is
a portfolio-wide tail risk. We proxy USDT's peg via a stablecoin pair such as
USDC_USDT: when it drifts far from 1.0, USDT has likely depegged and new entries
should pause until it recovers.
"""
from __future__ import annotations

from decimal import Decimal


def depeg_deviation(stable_pair_price: Decimal) -> Decimal:
    """Absolute deviation of a stablecoin pair price from parity (1.0)."""
    return abs(stable_pair_price - Decimal("1"))


def is_depegged(stable_pair_price: Decimal | None, threshold_pct: float) -> bool:
    """True when the stablecoin pair has drifted beyond the threshold from 1.0."""
    if stable_pair_price is None or stable_pair_price <= 0:
        return False  # no signal -> don't false-alarm a halt
    return depeg_deviation(stable_pair_price) > Decimal(str(threshold_pct))
