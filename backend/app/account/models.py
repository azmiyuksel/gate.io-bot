from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class EquitySnapshot:
    """Computed account state for a single point in time."""

    cash_balance: Decimal
    available_balance: Decimal
    locked_balance: Decimal
    positions_value: Decimal
    total_equity: Decimal
    quote_currency: str = "USDT"
    source: str = "exchange"  # exchange | fallback
    balances: dict[str, dict] = field(default_factory=dict)
