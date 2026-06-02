"""Prometheus metrics for the API process.

Exposes request counters and a latency histogram, labelled by method, route
template (not the raw path, to avoid unbounded cardinality) and status code.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "route", "status"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
)


def record_request(method: str, route: str, status: int, duration_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, route=route, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, route=route).observe(duration_seconds)


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
