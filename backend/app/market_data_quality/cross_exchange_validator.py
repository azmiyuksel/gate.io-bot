"""Cross-exchange price consistency validation.

Compares the primary feed price against one or more reference exchanges. Reference
prices are supplied by pluggable callables (``PriceSource``) so the module stays
decoupled from any specific exchange SDK and is trivially testable. A divergence
beyond the configured tolerance raises a ``cross_exchange_divergence`` anomaly.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from app.market_data_quality.models import AnomalyFinding, AnomalyType

# A price source resolves a normalized symbol to its last price (or None).
PriceSource = Callable[[str], Decimal | None]


@dataclass
class CrossExchangeResult:
    reference_prices: dict[str, float]
    max_divergence_pct: float
    diverged: bool
    finding: AnomalyFinding | None


class CrossExchangeValidator:
    def __init__(
        self,
        sources: dict[str, PriceSource] | None = None,
        threshold_pct: float = 0.01,
    ) -> None:
        self.sources = sources or {}
        self.threshold = threshold_pct

    def register_source(self, name: str, source: PriceSource) -> None:
        self.sources[name] = source

    def validate(self, symbol: str, primary_price: Decimal) -> CrossExchangeResult:
        if primary_price is None or primary_price <= 0 or not self.sources:
            return CrossExchangeResult({}, 0.0, False, None)

        primary = float(primary_price)
        references: dict[str, float] = {}
        max_div = 0.0
        worst_name = ""

        for name, source in self.sources.items():
            try:
                ref = source(symbol)
            except Exception:
                ref = None
            if ref is None or ref <= 0:
                continue
            ref_f = float(ref)
            references[name] = ref_f
            divergence = abs(primary - ref_f) / ref_f
            if divergence > max_div:
                max_div = divergence
                worst_name = name

        diverged = max_div > self.threshold
        finding = None
        if diverged:
            finding = AnomalyFinding(
                anomaly_type=AnomalyType.cross_exchange_divergence,
                severity="CRITICAL" if max_div > self.threshold * 3 else "WARNING",
                detail=(
                    f"{symbol} primary {primary:.6f} diverges {max_div:.4%} "
                    f"from {worst_name} (> {self.threshold:.4%})"
                ),
                observed_value=max_div,
                threshold_value=self.threshold,
                detection_method="cross_exchange",
            )
        return CrossExchangeResult(references, max_div, diverged, finding)
