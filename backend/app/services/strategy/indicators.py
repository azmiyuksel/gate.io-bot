from decimal import Decimal


def ema(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    multiplier = Decimal("2") / Decimal(period + 1)
    current = sum(values[:period]) / Decimal(period)
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def rsi(values: list[Decimal], period: int = 14) -> Decimal | None:
    if len(values) <= period:
        return None
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for previous, current in zip(values[-period - 1 : -1], values[-period:]):
        change = current - previous
        gains.append(max(change, Decimal("0")))
        losses.append(abs(min(change, Decimal("0"))))
    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def atr(candles: list[dict], period: int = 14) -> Decimal | None:
    if len(candles) <= period:
        return None
    ranges: list[Decimal] = []
    for previous, current in zip(candles[-period - 1 : -1], candles[-period:]):
        high = Decimal(str(current["high"]))
        low = Decimal(str(current["low"]))
        prev_close = Decimal(str(previous["close"]))
        ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(ranges) / Decimal(period)
