"""Session / time-of-day entry filter.

Crypto liquidity is not uniform across the day or week: some UTC hours and the
weekend are markedly thinner, so the same market order pays more slippage and
breakouts fail more often. Skipping NEW entries in those low-liquidity windows
(open positions are still managed) is a cheap, structural edge improvement.
"""

from __future__ import annotations

from datetime import datetime


def entry_allowed(
    now: datetime, blocked_hours: set[int], block_weekend: bool
) -> tuple[bool, str]:
    """Whether a NEW entry is allowed at ``now`` (interpreted in UTC).

    Returns (allowed, reason). ``blocked_hours`` is a set of UTC hours (0-23) to
    skip; ``block_weekend`` skips Saturday/Sunday (UTC). An empty blocklist and
    a false weekend flag always allow (the filter is a no-op)."""
    # weekday(): Monday=0 .. Saturday=5, Sunday=6.
    if block_weekend and now.weekday() >= 5:
        return False, f"weekend_session_block (utc weekday={now.weekday()})"
    if now.hour in blocked_hours:
        return False, f"low_liquidity_hour_block (utc hour={now.hour})"
    return True, "allowed"
