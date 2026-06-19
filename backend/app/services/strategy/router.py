"""Regime-aware strategy routing.

The regime FILTER (``RegimeSignalFilter``) only ever *blocks* a strategy that is
mismatched to the current regime — so a momentum bot simply goes flat in a range.
Routing is the profit complement: instead of going flat, run the strategy that
actually has positive expectancy in that regime.

- Trend / breakout / volatile regimes favour MOMENTUM (ride the move; a fixed
  take-profit would cut the fat right tail that is the edge).
- Range / low-volatility regimes favour MEAN-REVERSION (fade the band extremes;
  a momentum breakout there mostly buys the top and sells the bottom).

The mapping is deliberately consistent with ``RegimeSignalFilter`` so the routed
strategy is always one the filter will then ALLOW (routing picks it, the filter
confirms it). Off by default — enable with ``REGIME_ROUTING_ENABLED=true``.
"""

from __future__ import annotations

from app.models.enums import MarketRegimeType
from app.services.strategy.momentum_breakout import STRATEGY_NAME as MOMENTUM_NAME
from app.services.strategy.signals import STRATEGY_NAME as REVERSION_NAME

# Regime -> the strategy family with positive expectancy in it.
_REGIME_TO_STRATEGY: dict[MarketRegimeType, str] = {
    MarketRegimeType.trending_bull: MOMENTUM_NAME,
    MarketRegimeType.trending_bear: MOMENTUM_NAME,
    MarketRegimeType.breakout_phase: MOMENTUM_NAME,
    MarketRegimeType.high_volatility: MOMENTUM_NAME,
    MarketRegimeType.sideways: REVERSION_NAME,
    MarketRegimeType.low_volatility: REVERSION_NAME,
}


def route_strategy_name(regime: MarketRegimeType, default: str) -> str:
    """Return the strategy name best suited to ``regime``.

    Falls back to ``default`` for any regime not in the map (defensive — every
    enum member is mapped today, so this only triggers if a new regime is added
    without updating this table)."""
    return _REGIME_TO_STRATEGY.get(regime, default)
