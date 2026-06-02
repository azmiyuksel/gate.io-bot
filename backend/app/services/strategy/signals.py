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

    def evaluate(self, candles: list[dict]) -> Signal:
        if len(candles) < 210:
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

        if last_price <= ema_200:
            return Signal(False, "below_200_ema")
        if rsi_14 >= Decimal("35"):
            return Signal(False, "rsi_not_oversold")

        distance_to_ema20 = abs(last_price - ema_20) / ema_20
        if distance_to_ema20 > Decimal("0.01"):
            return Signal(False, "not_near_20_ema")

        daily_range = max(closes[-24:]) - min(closes[-24:])
        if daily_range / last_price > Decimal("0.08"):
            return Signal(False, "excessive_24h_volatility")

        return Signal(True, "long_entry", last_price, atr_14)
