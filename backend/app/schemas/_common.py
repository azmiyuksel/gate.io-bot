"""Shared query-parameter validation for API endpoints.

Validates ``symbol`` and ``timeframe`` query parameters to reject arbitrary
user input before it reaches the database layer.  All read-only ORM filters
use parameterized queries so SQL injection is not a concern, but bad input
still wastes DB round-trips and produces confusing empty results.
"""
import re
from typing import Annotated

from fastapi import Query

_SYMBOL_RE = re.compile(r"^[A-Z0-9_]{2,20}$")
_TIMEFRAME_RE = re.compile(r"^(1m|5m|15m|30m|1h|4h|8h|1d|7d|30d)$")
_KNOWLEDGE_TYPE_RE = re.compile(r"^(feature|pattern|hypothesis|meta)$")
_STATUS_RE = re.compile(r"^(active|inactive|promoted|rejected|pending|awaiting_approval|approved|rejected)$")


def _validate_symbol(v: str) -> str:
    if not _SYMBOL_RE.match(v):
        raise ValueError(f"Invalid symbol format: {v!r} (expected 2-20 uppercase alphanumeric/underscore)")
    return v


def _validate_timeframe(v: str) -> str:
    if not _TIMEFRAME_RE.match(v):
        raise ValueError(f"Invalid timeframe: {v!r} (expected 1m,5m,15m,30m,1h,4h,8h,1d,7d,30d)")
    return v


ValidSymbol = Annotated[str, Query(description="Trading pair symbol (e.g. BTC_USDT)")]
ValidTimeframe = Annotated[str, Query(description="Candle timeframe (e.g. 1h)")]
OptionalSymbol = Annotated[str | None, Query(description="Trading pair symbol")]
OptionalTimeframe = Annotated[str | None, Query(description="Candle timeframe")]
