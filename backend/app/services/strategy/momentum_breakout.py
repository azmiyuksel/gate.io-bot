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
        self.vol_spike_mult = Decimal(str(s.momentum_vol_spike_mult))
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

        # Volume expansion vs the recent average (base volume; fall back to quote/price).
        # Use the last closed candle's volume for comparison — the forming bar has
        # incomplete volume that would artificially fail the check.
        vol_ratio = self._volume_ratio(candles)

        up_momentum = ema_f > ema_s and last_price > ema_t
        down_momentum = ema_f < ema_s and last_price < ema_t
        vol_ok = vol_ratio >= self.vol_spike_mult
        atr_ok = atr_pct >= self.min_atr_pct

        diag = {
            "rsi": float(rsi_v),
            "ema_fast": float(ema_f),
            "ema_slow": float(ema_s),
            "ema_trend": float(ema_t),
            "price": float(last_price),
            "atr_pct": float(atr_pct),
            "vol_ratio": float(vol_ratio),
        }

        if not atr_ok:
            return Signal(False, "", "atr_too_low", diagnostics=diag)
        if not vol_ok:
            return Signal(False, "", "low_volume", diagnostics=diag)

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

    def _volume_ratio(self, candles: list[dict]) -> Decimal:
        base_volumes: list[Decimal] = []
        last_closed_idx = -1
        for i, c in enumerate(candles):
            vol = c.get("volume")
            if vol is not None:
                base_volumes.append(Decimal(str(vol)))
            elif c.get("quote_volume") is not None and c.get("close"):
                close = Decimal(str(c["close"]))
                base_volumes.append(Decimal(str(c["quote_volume"])) / close if close > 0 else Decimal("0"))
            else:
                base_volumes.append(Decimal("0"))
            if c.get("closed", True):
                last_closed_idx = i
        if len(base_volumes) < 20:
            return Decimal("1")
        recent = base_volumes[-20:]
        avg = sum(recent) / Decimal(len(recent))
        # Use the last closed candle's volume; fall back to the very last bar
        # if none are marked (e.g. tests that omit the field).
        if last_closed_idx >= 0 and last_closed_idx < len(base_volumes):
            last_vol = base_volumes[last_closed_idx]
        else:
            last_vol = base_volumes[-1]
        return last_vol / avg if avg > 0 else Decimal("1")
