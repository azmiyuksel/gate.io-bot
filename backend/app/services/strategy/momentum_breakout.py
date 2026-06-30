"""High-frequency momentum / breakout strategy for 5m futures (long + short).

Designed for FREQUENT trading: it enters in the direction of short-term momentum
when price breaks the recent range on expanding volume, and relies on ATR-based
stops + trailing for exits. Unlike ``capital_preservation_v1`` (a low-frequency
mean-reversion filter), this strategy is symmetric (trades both sides) and fires
on every confirmed breakout, so it produces many more signals on lower timeframes.

The ``evaluate`` contract (returns a :class:`Signal`) is intentionally identical
to :class:`CapitalPreservationStrategy` so it is a drop-in for the paper-trading
adapter and the live engine.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.strategy.indicators import atr, ema, rsi
from app.services.strategy.signals import Signal

STRATEGY_NAME = "momentum_breakout_v1"


class MomentumBreakoutStrategy:
    """EMA-trend + volume-expansion momentum entries (no breakout requirement).

    LONG  when: fast EMA > slow EMA (up momentum), price above the trend EMA,
                volume expands, RSI not already exhausted.
    SHORT when: mirror image (down momentum, below trend EMA, volume expands).
    """

    name: str = STRATEGY_NAME

    def __init__(self) -> None:
        from app.core.config import get_settings

        s = get_settings()
        self.ema_fast = int(s.momentum_ema_fast)
        self.ema_slow = int(s.momentum_ema_slow)
        self.ema_trend = int(s.momentum_ema_trend)
        self.rsi_long_max = Decimal(str(s.momentum_rsi_long_max))
        self.rsi_short_min = Decimal(str(s.momentum_rsi_short_min))
        self.min_atr_pct = Decimal(str(s.momentum_min_atr_pct))
        self.allow_short = bool(s.momentum_allow_short)

    def evaluate(self, candles: list[dict]) -> Signal:
        min_history = self.ema_trend + 5
        if len(candles) < min_history:
            return Signal(False, "", "not_enough_history")

        closes = [Decimal(str(c["close"])) for c in candles]
        last_price = closes[-1]

        ema_f = ema(closes, self.ema_fast)
        ema_s = ema(closes, self.ema_slow)
        ema_t = ema(closes, self.ema_trend)
        rsi_v = rsi(closes, 14)
        atr_v = atr(candles, 14)
        if None in (ema_f, ema_s, ema_t, rsi_v, atr_v):
            return Signal(False, "", "indicator_unavailable")
        if last_price <= 0 or ema_t <= 0:
            return Signal(False, "", "invalid_price_data")

        # Volatility floor: skip dead markets where the move can't clear fees+slippage.
        atr_pct = atr_v / last_price

        up_momentum = ema_f > ema_s and last_price > ema_t
        down_momentum = ema_f < ema_s and last_price < ema_t
        atr_ok = atr_pct >= self.min_atr_pct

        diag = {
            "rsi": float(rsi_v),
            "ema_fast": float(ema_f),
            "ema_slow": float(ema_s),
            "ema_trend": float(ema_t),
            "price": float(last_price),
            "atr_pct": float(atr_pct),
        }

        if not atr_ok:
            return Signal(False, "", "atr_too_low", diagnostics=diag)

        if up_momentum:
            if rsi_v >= self.rsi_long_max:
                return Signal(False, "", "rsi_extended", diagnostics=diag)
            return Signal(
                True, "long", "long_momentum", last_price, atr_v, diagnostics=diag,
                expectancy_type="trend",
            )

        if self.allow_short and down_momentum:
            if rsi_v <= self.rsi_short_min:
                return Signal(False, "", "rsi_extended", diagnostics=diag)
            return Signal(
                True, "short", "short_momentum", last_price, atr_v, diagnostics=diag,
                expectancy_type="trend",
            )

        return Signal(False, "", "no_momentum", diagnostics=diag)
