"""Lightweight in-process rate limiter for sensitive endpoints (e.g. login).

A sliding-window counter keyed by an arbitrary string (client IP + email). This
is per-process; for multi-replica deployments back it with Redis instead. Kept
dependency-free so it works out of the box.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, prune_every: int = 500) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._prune_every = prune_every
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._ops = 0

    def _prune(self, cutoff: float, skip_key: str | None = None) -> None:
        """Drop keys whose hits have all aged out, bounding memory growth.

        *skip_key* exempts one key from pruning (the key about to be touched)
        so that a zero-window prune does not evict the entry we're about to use.
        """
        stale = [
            key
            for key, hits in self._hits.items()
            if key != skip_key and (not hits or hits[-1] <= cutoff)
        ]
        for key in stale:
            del self._hits[key]

    def is_allowed(self, key: str) -> bool:
        """Record an attempt and return False once the window limit is exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            self._ops += 1
            if self._ops % self._prune_every == 0:
                self._prune(cutoff, skip_key=key)
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return False
            hits.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
