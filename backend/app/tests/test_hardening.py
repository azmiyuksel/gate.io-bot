"""Tests for the security/robustness hardening (secrets guard, rate limiter)."""
import pytest

from app.core.config import Settings
from app.core.rate_limit import SlidingWindowRateLimiter


def test_production_rejects_default_secret():
    s = Settings(environment="production", secret_key="change-me", fernet_key="x")
    with pytest.raises(RuntimeError):
        s.validate_runtime_secrets()


def test_production_rejects_missing_fernet_key():
    s = Settings(environment="production", secret_key="a-strong-unique-secret", fernet_key="")
    with pytest.raises(RuntimeError):
        s.validate_runtime_secrets()


def test_local_warns_but_allows_default_secret():
    s = Settings(environment="local", secret_key="change-me", fernet_key="")
    warnings = s.validate_runtime_secrets()
    assert any("SECRET_KEY" in w for w in warnings)
    assert any("FERNET_KEY" in w for w in warnings)


def test_production_with_strong_secret_passes():
    s = Settings(environment="production", secret_key="a-strong-unique-secret", fernet_key="x", cors_origins="https://dashboard.example.com")
    assert s.validate_runtime_secrets() == []


def test_production_rejects_localhost_cors():
    s = Settings(environment="production", secret_key="a-strong-unique-secret", fernet_key="x", cors_origins="http://localhost:3000")
    with pytest.raises(RuntimeError, match="CORS"):
        s.validate_runtime_secrets()


def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert all(limiter.is_allowed("k") for _ in range(3))
    assert limiter.is_allowed("k") is False


def test_rate_limiter_prunes_stale_keys():
    # Tiny window + prune_every=1 so every call triggers a prune.
    limiter = SlidingWindowRateLimiter(max_attempts=5, window_seconds=0, prune_every=1)
    for i in range(10):
        limiter.is_allowed(f"key-{i}")
    # With a zero-length window every prior hit is immediately stale. The prune
    # runs before the new hit is appended, so at most 2 entries survive: the
    # current key's just-added hit and the previous key's hit (which becomes
    # stale on the *next* prune cycle).  Crucially, entries never grow unbounded.
    assert len(limiter._hits) <= 1


def test_rate_limiter_reset_clears_key():
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.is_allowed("k") is True
    assert limiter.is_allowed("k") is False
    limiter.reset("k")
    assert limiter.is_allowed("k") is True
