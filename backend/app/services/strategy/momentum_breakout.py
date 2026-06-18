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
    """EMA-trend + Donchian breakout + volume-expansion momentum entries.

    LONG  when: fast EMA > slow EMA (up momentum), price above the trend EMA,
                close breaks above the prior N-bar high, volume expands, RSI not
                already exhausted, and ATR is large enough to clear costs.
    SHORT when: the mirror image (down momentum, below trend EMA, breaks the
                prior N-bar low, volume expands, RSI not already exhausted).
    """

    name: str = STRATEGY_NAME

    def __init__(self) -> None:
        from app.core.config import get_settings

        s = get_settings()
        self.ema_fast = int(s.momentum_ema_fast)
        self.ema_slow = int(s.momentum_ema_slow)
        self.ema_trend = int(s.momentum_ema_trend)
        self.donchian_lookback = int(s.momentum_donchian_lookback)
        self.vol_spike_mult = Decimal(str(s.momentum_vol_spike_mult))
        self.rsi_long_max = Decimal(str(s.momentum_rsi_long_max))
        self.rsi_short_min = Decimal(str(s.momentum_rsi_short_min))
        self.min_atr_pct = Decimal(str(s.momentum_min_atr_pct))
        self.breakout_buffer_atr = Decimal(str(s.momentum_breakout_buffer_atr))
        # Round-trip cost floor: a breakout smaller than the realistic cost of
        # round-tripping (2x taker + spread + slippage) is instantly underwater,
        # so the breakout buffer is floored at this fraction of price. Without
        # it, a "breakout" can fire inside the bid-ask and bleed fees on every
        # such signal — a silent edge leak for a frequent-trading strategy.
        self.round_trip_cost_pct = Decimal(str(s.momentum_round_trip_cost_pct))
        # Symmetric strategy: shorts are always allowed (futures). Kept as a flag so
        # a long-only (spot) deployment can disable shorts without code changes.
        self.allow_short = bool(s.momentum_allow_short)

    def evaluate(self, candles: list[dict]) -> Signal:
        min_history = max(self.ema_trend, self.donchian_lookback) + 5
        if len(candles) < min_history:
            return Signal(False, "", "not_enough_history")

        closes = [Decimal(str(c["close"])) for c in candles]
        highs = [Decimal(str(c["high"])) for c in candles]
        lows = [Decimal(str(c["low"])) for c in candles]
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
        vol_ratio = self._volume_ratio(candles)

        # Breakout reference levels: the prior N-bar extreme EXCLUDING the forming bar.
        window_high = max(highs[-self.donchian_lookback - 1 : -1])
        window_low = min(lows[-self.donchian_lookback - 1 : -1])
        # Buffer floored at the round-trip cost: a breakout must clear the prior
        # extreme by AT LEAST the cost of round-tripping, otherwise it fires
        # inside the bid-ask+fees band and is instantly underwater. The ATR-based
        # buffer is the noise filter; the cost floor is the economic floor.
        atr_buffer = atr_v * self.breakout_buffer_atr
        cost_buffer = last_price * self.round_trip_cost_pct
        buffer = max(atr_buffer, cost_buffer)

        up_momentum = ema_f > ema_s and last_price > ema_t
        down_momentum = ema_f < ema_s and last_price < ema_t
        breaks_high = last_price > window_high + buffer
        breaks_low = last_price < window_low - buffer
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
            "window_high": float(window_high),
            "window_low": float(window_low),
        }

        if not atr_ok:
            return Signal(False, "", "atr_too_low", diagnostics=diag)
        if not vol_ok:
            return Signal(False, "", "low_volume", diagnostics=diag)

        if up_momentum and breaks_high:
            if rsi_v >= self.rsi_long_max:
                return Signal(False, "", "rsi_extended", diagnostics=diag)
            return Signal(
                True, "long", "long_breakout", last_price, atr_v, diagnostics=diag,
                # Trend-following: no fixed take-profit. Let winners run via
                # trailing + breakeven — a fixed R:R TP cuts the big winners
                # that are the main edge of a breakout strategy.
                expectancy_type="trend",
            )

        if self.allow_short and down_momentum and breaks_low:
            if rsi_v <= self.rsi_short_min:
                return Signal(False, "", "rsi_extended", diagnostics=diag)
            return Signal(
                True, "short", "short_breakout", last_price, atr_v, diagnostics=diag,
                expectancy_type="trend",
            )

        if not (up_momentum or down_momentum):
            return Signal(False, "", "no_momentum", diagnostics=diag)
        return Signal(False, "", "no_breakout", diagnostics=diag)

    def _volume_ratio(self, candles: list[dict]) -> Decimal:
        base_volumes: list[Decimal] = []
        for c in candles:
            vol = c.get("volume")
            if vol is not None:
                base_volumes.append(Decimal(str(vol)))
            elif c.get("quote_volume") is not None and c.get("close"):
                close = Decimal(str(c["close"]))
                base_volumes.append(Decimal(str(c["quote_volume"])) / close if close > 0 else Decimal("0"))
            else:
                base_volumes.append(Decimal("0"))
        if len(base_volumes) < 20:
            return Decimal("1")
        recent = base_volumes[-20:]
        avg = sum(recent) / Decimal(len(recent))
        return base_volumes[-1] / avg if avg > 0 else Decimal("1")
