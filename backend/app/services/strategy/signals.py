from dataclasses import dataclass
from decimal import Decimal

from app.services.strategy.indicators import atr, ema, rsi

# Canonical strategy identifier. Must match StrategySettings.name and the name
# used by the paper-trading adapter so health/regime records key consistently.
STRATEGY_NAME = "capital_preservation_v1"


@dataclass(frozen=True)
class Signal:
    should_buy: bool
    reason: str
    entry_price: Decimal | None = None
    atr_value: Decimal | None = None


class CapitalPreservationStrategy:
    name: str = STRATEGY_NAME

    def __init__(self) -> None:
        # Entry thresholds are configurable so they can be tuned per market
        # without code changes. The 24h-range filter especially is asset
        # dependent — 8% is tight for many crypto pairs that routinely move more.
        from app.core.config import get_settings

        settings = get_settings()
        self.rsi_threshold = Decimal(str(settings.strategy_rsi_threshold))
        self.ema20_distance_pct = Decimal(str(settings.strategy_ema20_distance_pct))
        self.max_24h_range_pct = Decimal(str(settings.strategy_max_24h_range_pct))
        self.daily_range_candles = settings.strategy_daily_range_candles
        # Volume filter: reject entries when current volume is below this fraction
        # of the recent average volume. Default 50%.
        self.min_volume_ratio = Decimal(str(getattr(settings, "strategy_min_volume_ratio", "0.5")))

    def evaluate(self, candles: list[dict]) -> Signal:
        if len(candles) < 200:
            return Signal(False, "not_enough_history")

        closes = [Decimal(str(candle["close"])) for candle in candles]
        last_price = closes[-1]
        ema_200 = ema(closes, 200)
        ema_20 = ema(closes, 20)
        rsi_14 = rsi(closes, 14)
        atr_14 = atr(candles, 14)
        if None in (ema_200, ema_20, rsi_14, atr_14):
            return Signal(False, "indicator_unavailable")

        # Guard against degenerate feeds: a zero/negative price or EMA would make
        # the ratio checks below raise ZeroDivisionError and crash the scan.
        if last_price <= 0 or ema_20 <= 0 or ema_200 <= 0:
            return Signal(False, "invalid_price_data")

        # --- Volume filter: reject low-volume entries ---
        # Extract base volumes from candles (index 6 in GateIO v4 response, or derived from quote_volume/close)
        base_volumes: list[Decimal] = []
        for candle in candles:
            # GateIOClient.candles() returns dicts with "volume" key (base volume)
            if "volume" in candle and candle["volume"] is not None:
                base_volumes.append(Decimal(str(candle["volume"])))
            elif "quote_volume" in candle and candle["quote_volume"] is not None:
                # Fallback: derive base volume from quote volume / close
                close = Decimal(str(candle["close"])) if candle["close"] is not None else Decimal("0")
                if close > 0:
                    base_volumes.append(Decimal(str(candle["quote_volume"])) / close)
                else:
                    base_volumes.append(Decimal("0"))
            else:
                base_volumes.append(Decimal("0"))

        if len(base_volumes) >= 20:  # Need enough samples for meaningful average
            recent_volumes = base_volumes[-20:]
            avg_volume = sum(recent_volumes) / Decimal(len(recent_volumes))
            current_volume = base_volumes[-1]
            if avg_volume > 0 and current_volume / avg_volume < self.min_volume_ratio:
                return Signal(False, "low_volume")

        if False:  # EMA200 trend filter disabled for paper trading
            if last_price <= ema_200:
                return Signal(False, "below_200_ema")
        if rsi_14 >= self.rsi_threshold:
            return Signal(False, "rsi_not_oversold")

        distance_to_ema20 = abs(last_price - ema_20) / ema_20
        if distance_to_ema20 > self.ema20_distance_pct:
            return Signal(False, "not_near_20_ema")

        n = min(self.daily_range_candles, len(closes))
        daily_range = max(closes[-n:]) - min(closes[-n:])
        if daily_range / last_price > self.max_24h_range_pct:
            return Signal(False, "excessive_24h_volatility")

        return Signal(True, "long_entry", last_price, atr_14)
