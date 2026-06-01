"""Normalization helpers applied before validation.

Brings heterogeneous feed payloads into a single canonical form: UTC timestamps,
uppercased ``BASE_QUOTE`` symbols, consistent decimal precision and volume
scaling. Idempotent — re-normalizing an already-normalized candle is a no-op.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from app.market_data_quality.models import CandleData

_PRICE_QUANT = Decimal("0.0000000001")  # 10 dp, matches Numeric(24, 10)
_VOLUME_QUANT = Decimal("0.0000000001")


def normalize_symbol(symbol: str, quote_hint: str = "USDT") -> str:
    """Canonicalize to ``BASE_QUOTE`` upper-case with an underscore separator."""
    s = symbol.strip().upper().replace("-", "_").replace("/", "_")
    if "_" in s:
        return s
    # No separator (e.g. "BTCUSDT"): split on a known quote suffix.
    for quote in (quote_hint.upper(), "USDT", "USDC", "USD", "BTC", "ETH"):
        if s.endswith(quote) and len(s) > len(quote):
            return f"{s[: -len(quote)]}_{quote}"
    return s


def normalize_timestamp(timestamp) -> datetime:
    """Return a timezone-aware UTC datetime from epoch seconds/ms or datetime."""
    if isinstance(timestamp, datetime):
        return timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    value = int(timestamp)
    # Heuristic: treat 13-digit values as milliseconds.
    if value > 10_000_000_000:
        value //= 1000
    return datetime.fromtimestamp(value, UTC)


def _round_price(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_PRICE_QUANT, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _round_volume(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_VOLUME_QUANT, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError):
        return Decimal("0")


class DataNormalizer:
    def __init__(self, quote_hint: str = "USDT", volume_scale: Decimal = Decimal("1")) -> None:
        self.quote_hint = quote_hint
        self.volume_scale = volume_scale

    def normalize_candle(self, candle: CandleData) -> CandleData:
        return CandleData(
            symbol=normalize_symbol(candle.symbol, self.quote_hint),
            timeframe=candle.timeframe,
            timestamp=normalize_timestamp(candle.timestamp),
            open=_round_price(candle.open),
            high=_round_price(candle.high),
            low=_round_price(candle.low),
            close=_round_price(candle.close),
            volume=_round_volume(Decimal(str(candle.volume)) * self.volume_scale),
            source=candle.source,
        )

    def from_exchange_dict(
        self, raw: dict, symbol: str, timeframe: str, source: str = "gateio"
    ) -> CandleData:
        """Build a normalized CandleData from a Gate.io-style candle dict."""
        return self.normalize_candle(
            CandleData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=raw["timestamp"],
                open=Decimal(str(raw["open"])),
                high=Decimal(str(raw["high"])),
                low=Decimal(str(raw["low"])),
                close=Decimal(str(raw["close"])),
                volume=Decimal(str(raw.get("volume", "0"))),
                source=source,
            )
        )
