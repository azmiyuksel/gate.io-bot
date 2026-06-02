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
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Record an attempt and return False once the window limit is exceeded."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= self.max_attempts:
                return False
            hits.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)
