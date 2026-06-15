from dataclasses import dataclass
from decimal import Decimal

from app.services.strategy.indicators import atr, ema, rsi

# Canonical strategy identifier. Must match StrategySettings.name and the name
# used by the paper-trading adapter so health/regime records key consistently.
STRATEGY_NAME = "capital_preservation_v1"


@dataclass(frozen=True)
class Signal:
    should_enter: bool
    direction: str  # "long" or "short"
    reason: str
    entry_price: Decimal | None = None
    atr_value: Decimal | None = None
    diagnostics: dict | None = None


class CapitalPreservationStrategy:
    name: str = STRATEGY_NAME

    def __init__(self) -> None:
        # Entry thresholds are configurable so they can be tuned per market
        # without code changes. The 24h-range filter especially is asset
        # dependent — 8% is tight for many crypto pairs that routinely move more.
        from app.core.config import get_settings

        settings = get_settings()
        self.rsi_threshold = Decimal(str(settings.strategy_rsi_threshold))
        self.rsi_overbought = Decimal(str(settings.strategy_rsi_overbought))
        self.ema20_distance_pct = Decimal(str(settings.strategy_ema20_distance_pct))
        self.max_24h_range_pct = Decimal(str(settings.strategy_max_24h_range_pct))
        self.daily_range_candles = settings.strategy_daily_range_candles
        self.min_volume_ratio = Decimal(str(settings.strategy_min_volume_ratio))
        self.trend_filter_enabled = settings.strategy_trend_filter_enabled

    def evaluate(self, candles: list[dict]) -> Signal:
        if len(candles) < 200:
            return Signal(False, "", "not_enough_history")

        closes = [Decimal(str(candle["close"])) for candle in candles]
        last_price = closes[-1]
        ema_200 = ema(closes, 200)
        ema_20 = ema(closes, 20)
        rsi_14 = rsi(closes, 14)
        atr_14 = atr(candles, 14)
        if None in (ema_200, ema_20, rsi_14, atr_14):
            return Signal(False, "", "indicator_unavailable")

        if last_price <= 0 or ema_20 <= 0 or ema_200 <= 0:
            return Signal(False, "", "invalid_price_data")

        base_volumes: list[Decimal] = []
        for candle in candles:
            if "volume" in candle and candle["volume"] is not None:
                base_volumes.append(Decimal(str(candle["volume"])))
            elif "quote_volume" in candle and candle["quote_volume"] is not None:
                close = Decimal(str(candle["close"])) if candle["close"] is not None else Decimal("0")
                if close > 0:
                    base_volumes.append(Decimal(str(candle["quote_volume"])) / close)
                else:
                    base_volumes.append(Decimal("0"))
            else:
                base_volumes.append(Decimal("0"))

        vol_ratio = Decimal("1")
        if len(base_volumes) >= 20:
            recent_volumes = base_volumes[-20:]
            avg_volume = sum(recent_volumes) / Decimal(len(recent_volumes))
            current_volume = base_volumes[-1]
            if avg_volume > 0:
                vol_ratio = current_volume / avg_volume
                if vol_ratio < self.min_volume_ratio:
                    return Signal(False, "", "low_volume",
                        diagnostics={"rsi": float(rsi_14), "vol_ratio": float(vol_ratio)})

        distance_to_ema20 = abs(last_price - ema_20) / ema_20
        distance_ok = distance_to_ema20 <= self.ema20_distance_pct

        n = min(self.daily_range_candles, len(closes))
        daily_range = max(closes[-n:]) - min(closes[-n:])
        daily_range_pct = daily_range / last_price
        range_ok = daily_range_pct <= self.max_24h_range_pct

        trend_up = last_price > ema_200
        rsi_oversold = rsi_14 < self.rsi_threshold

        diag = {
            "rsi": float(rsi_14),
            "ema20": float(ema_20),
            "ema200": float(ema_200),
            "price": float(last_price),
            "dist_ema20_pct": float(distance_to_ema20),
            "range_pct": float(daily_range_pct),
            "vol_ratio": float(vol_ratio),
        }

        if trend_up and rsi_oversold and distance_ok and range_ok:
            return Signal(True, "long", "long_entry", last_price, atr_14, diagnostics=diag)

        if self.trend_filter_enabled:
            trend_down = last_price < ema_200
            rsi_overbought = rsi_14 > self.rsi_overbought
            if trend_down and rsi_overbought and distance_ok and range_ok:
                return Signal(True, "short", "short_entry", last_price, atr_14, diagnostics=diag)

        if self.trend_filter_enabled:
            if not trend_up and not trend_down:
                return Signal(False, "", "not_trending", diagnostics=diag)
            if trend_up and not rsi_oversold:
                return Signal(False, "", "rsi_not_oversold", diagnostics=diag)
            if trend_down and not rsi_overbought and rsi_14 <= self.rsi_overbought:
                return Signal(False, "", "rsi_not_overbought", diagnostics=diag)
        else:
            if not rsi_oversold:
                return Signal(False, "", "rsi_not_oversold", diagnostics=diag)
        if not distance_ok:
            return Signal(False, "", "not_near_20_ema", diagnostics=diag)
        if not range_ok:
            return Signal(False, "", "excessive_24h_volatility", diagnostics=diag)
        return Signal(False, "", "no_signal", diagnostics=diag)
