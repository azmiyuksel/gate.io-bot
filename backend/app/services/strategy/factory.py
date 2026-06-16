"""Single source of truth for instantiating a trading strategy by name.

Both the live engine and the paper-trading adapter build their strategy through
here so the two stay in lock-step ("paper mirrors live"). Add new strategies in
one place and both paths pick them up.
"""

from __future__ import annotations

from app.services.strategy.momentum_breakout import STRATEGY_NAME as MOMENTUM_NAME
from app.services.strategy.momentum_breakout import MomentumBreakoutStrategy
from app.services.strategy.signals import STRATEGY_NAME as CAPITAL_PRESERVATION_NAME
from app.services.strategy.signals import CapitalPreservationStrategy

KNOWN_STRATEGIES = (MOMENTUM_NAME, CAPITAL_PRESERVATION_NAME)


def build_strategy(name: str):
    """Return a fresh strategy instance for ``name``.

    Unknown names fall back to the frequent momentum strategy (the project
    default) rather than raising, so a typo can never silently disable trading.
    """
    if name == CAPITAL_PRESERVATION_NAME:
        return CapitalPreservationStrategy()
    return MomentumBreakoutStrategy()
