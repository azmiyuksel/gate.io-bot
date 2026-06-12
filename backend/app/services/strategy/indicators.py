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
    # Compute all price changes
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(c, Decimal("0")) for c in changes]
    losses = [abs(min(c, Decimal("0"))) for c in changes]
    # Seed with SMA of first `period` values, then apply Wilder smoothing
    avg_gain = sum(gains[:period]) / Decimal(period)
    avg_loss = sum(losses[:period]) / Decimal(period)
    alpha = Decimal("1") / Decimal(period)
    for g, loss_val in zip(gains[period:], losses[period:]):
        avg_gain = avg_gain * (Decimal("1") - alpha) + g * alpha
        avg_loss = avg_loss * (Decimal("1") - alpha) + loss_val * alpha
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
