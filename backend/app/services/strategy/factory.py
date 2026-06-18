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

    Hard-fails on an unknown name. The previous behaviour fell back to the
    momentum strategy "so a typo can never silently disable trading" — but a
    typo here silently runs the WRONG strategy, which is worse: it trades an
    unvalidated strategy on live capital. A typo must surface immediately so
    the operator fixes the config instead of discovering the mismatch from
    a PnL swing.
    """
    if name == CAPITAL_PRESERVATION_NAME:
        return CapitalPreservationStrategy()
    if name == MOMENTUM_NAME:
        return MomentumBreakoutStrategy()
    raise ValueError(
        f"Unknown strategy '{name}'. Known strategies: {list(KNOWN_STRATEGIES)}. "
        f"Set LIVE_STRATEGY / PAPER_STRATEGY to one of these (check .env for a typo)."
    )
