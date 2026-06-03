"""Real exchange account balance and equity tracking.

Replaces the previously hard-coded equity value used by the scheduler, risk
manager and dashboard. Fetches spot balances from Gate.io, marks open
positions to market, persists a snapshot and degrades gracefully to the last
known snapshot (or a configured fallback) when the exchange is unreachable.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.market_data.price_cache import price_cache
from app.models.entities import AccountSnapshot
from app.account.models import EquitySnapshot
from app.services.exchange.gateio import GateIOClient

logger = logging.getLogger(__name__)


class AccountManager:
    def __init__(self, db: Session, client: GateIOClient | None = None) -> None:
        self.db = db
        self.client = client
        self.settings = get_settings()
        self.quote = self.settings.default_quote_currency
        self.stablecoins = self.settings.stablecoin_set

    async def _price(self, currency: str) -> Decimal | None:
        symbol = f"{currency}_{self.quote}"
        cached = price_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            return await self.client.last_price(symbol)
        except Exception:
            return None

    async def fetch_snapshot(self) -> EquitySnapshot:
        """Build an equity snapshot from live balances, falling back on failure."""
        if self.client is None:
            return self._fallback_snapshot()
        try:
            raw = await self.client.balances()
        except Exception:
            logger.warning("Balance fetch failed; using fallback equity snapshot", exc_info=True)
            return self._fallback_snapshot()

        cash = available = locked = Decimal("0")
        positions_value = Decimal("0")
        balances: dict[str, dict] = {}

        for entry in raw or []:
            currency = entry.get("currency", "")
            avail = Decimal(str(entry.get("available", "0") or "0"))
            lock = Decimal(str(entry.get("locked", "0") or "0"))
            total = avail + lock
            if total <= 0:
                continue
            # Store as strings to preserve full Decimal precision in JSON.
            balances[currency] = {"available": str(avail), "locked": str(lock)}

            # The quote and other stablecoins count as cash (at par), not as
            # marked-to-market positions, so available/locked cash is classified
            # correctly across multi-stablecoin balances (USDT, USDC, ...).
            if currency == self.quote or currency.upper() in self.stablecoins:
                cash += total
                available += avail
                locked += lock
                continue

            price = await self._price(currency)
            if price is not None:
                positions_value += total * price

        total_equity = cash + positions_value
        return EquitySnapshot(
            cash_balance=cash,
            available_balance=available,
            locked_balance=locked,
            positions_value=positions_value,
            total_equity=total_equity,
            quote_currency=self.quote,
            source="exchange",
            balances=balances,
        )

    def _fallback_snapshot(self) -> EquitySnapshot:
        last = self.last_snapshot()
        if last is not None:
            return EquitySnapshot(
                cash_balance=last.cash_balance,
                available_balance=last.available_balance,
                locked_balance=last.locked_balance,
                positions_value=last.positions_value,
                total_equity=last.total_equity,
                quote_currency=last.quote_currency,
                source="fallback",
                balances=last.balances or {},
            )
        equity = Decimal(str(self.settings.fallback_equity))
        return EquitySnapshot(
            cash_balance=equity,
            available_balance=equity,
            locked_balance=Decimal("0"),
            positions_value=Decimal("0"),
            total_equity=equity,
            quote_currency=self.quote,
            source="fallback",
            balances={},
        )

    def persist(self, snapshot: EquitySnapshot) -> AccountSnapshot:
        record = AccountSnapshot(
            exchange="gateio",
            quote_currency=snapshot.quote_currency,
            cash_balance=snapshot.cash_balance,
            available_balance=snapshot.available_balance,
            locked_balance=snapshot.locked_balance,
            positions_value=snapshot.positions_value,
            total_equity=snapshot.total_equity,
            balances=snapshot.balances,
            source=snapshot.source,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    async def refresh(self) -> AccountSnapshot:
        return self.persist(await self.fetch_snapshot())

    def last_snapshot(self) -> AccountSnapshot | None:
        return (
            self.db.query(AccountSnapshot)
            .order_by(AccountSnapshot.created_at.desc(), AccountSnapshot.id.desc())
            .first()
        )

    def latest_equity(self) -> Decimal:
        """Synchronous best-effort equity for risk checks without a network call."""
        last = self.last_snapshot()
        if last is not None and last.total_equity > 0:
            return last.total_equity
        return Decimal(str(self.settings.fallback_equity))

    def snapshot_age_seconds(self) -> float | None:
        """Age of the most recent snapshot in seconds, or None if there is none."""
        last = self.last_snapshot()
        if last is None or last.created_at is None:
            return None
        created = last.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return (datetime.now(UTC) - created).total_seconds()

    def is_equity_stale(self) -> bool:
        """True when the latest equity is too old (or absent) to size risk against."""
        age = self.snapshot_age_seconds()
        if age is None:
            return True
        return age > self.settings.max_equity_staleness_seconds

    def peak_equity(self) -> Decimal:
        value = self.db.query(func.max(AccountSnapshot.total_equity)).scalar()
        if value is None:
            return self.latest_equity()
        return Decimal(str(value))

    def drawdown_pct(self) -> Decimal:
        peak = self.peak_equity()
        if peak <= 0:
            return Decimal("0")
        equity = self.latest_equity()
        return (peak - equity) / peak
