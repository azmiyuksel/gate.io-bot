from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Dict, Tuple
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Allocation, Portfolio, RebalanceEvent
from app.models.enums import RebalanceStatus, RebalanceTrigger


class PortfolioRebalancer:
    def __init__(self, db: Session) -> None:
        self.db = db

    def check_rebalance_triggers(
        self,
        portfolio: Portfolio,
        current_drawdown: Decimal,
        is_volatility_spike: bool
    ) -> Tuple[bool, RebalanceTrigger | None]:
        """
        Evaluates trigger conditions for portfolio rebalancing.

        When the most-recent event was skipped due to cost, time-based
        triggers are suppressed to prevent cheap-redundant-trigger loops.
        """
        settings = get_settings()
        # 1. Drawdown trigger (always fires regardless of last status)
        if current_drawdown > Decimal(str(settings.portfolio_rebalance_drawdown_pct)):
            return True, RebalanceTrigger.drawdown_threshold

        # 2. Volatility spike trigger
        if is_volatility_spike:
            return True, RebalanceTrigger.volatility_spike

        # 3. Scheduled weekly / monthly check
        last_event = (
            self.db.query(RebalanceEvent)
            .filter(RebalanceEvent.portfolio_id == portfolio.id)
            .order_by(RebalanceEvent.created_at.desc())
            .first()
        )
        
        now = datetime.now(UTC)
        if not last_event:
            return True, RebalanceTrigger.manual

        # Suppress time triggers when the last event was skipped
        if last_event.status == RebalanceStatus.skipped:
            return False, None

        # Time elapsed since last rebalance
        elapsed = now - last_event.created_at
        if elapsed >= timedelta(days=settings.portfolio_rebalance_monthly_days):
            return True, RebalanceTrigger.scheduled_monthly
        elif elapsed >= timedelta(days=settings.portfolio_rebalance_weekly_days):
            return True, RebalanceTrigger.scheduled_weekly

        return False, None

    def execute_rebalance(
        self,
        portfolio: Portfolio,
        target_weights: Dict[str, float],
        trigger_reason: RebalanceTrigger
    ) -> RebalanceEvent:
        """
        Saves the rebalanced allocation weights to the DB and records a RebalanceEvent.

        Skips the rebalance if the estimated round-trip cost exceeds the
        maximum allowed deviation — avoiding unnecessary churn.
        """
        # Fetch current allocations
        current_allocs = (
            self.db.query(Allocation)
            .filter(Allocation.portfolio_id == portfolio.id)
            .all()
        )
        previous_weights = {a.target_name: float(a.weight) for a in current_allocs}

        # Estimate rebalance cost and skip if deviation is trivial
        cost_bps = get_settings().rebalance_cost_bps
        total_deviation = sum(
            abs(target_weights.get(name, 0.0) - w)
            for name, w in previous_weights.items()
        )
        # If total turnover is less than 2x the round-trip cost, skip
        if total_deviation > 0 and (cost_bps / 10000) * 2 > total_deviation:
            event = RebalanceEvent(
                portfolio_id=portfolio.id,
                trigger_reason=trigger_reason,
                previous_weights=previous_weights,
                new_weights=target_weights,
                execution_log=f"Skipped: total deviation {total_deviation:.4f} < 2x cost ({cost_bps} bps)",
                status=RebalanceStatus.skipped
            )
            self.db.add(event)
            self.db.commit()
            return event

        # Clear existing allocations and insert new ones atomically
        # within a single savepoint so a crash between delete and insert
        # cannot leave the portfolio with zero allocations.
        old_allocs = (
            self.db.query(Allocation)
            .filter(Allocation.portfolio_id == portfolio.id)
            .all()
        )
        for a in old_allocs:
            self.db.delete(a)
        self.db.flush()  # stage deletions without committing yet

        # Save new allocations
        execution_logs = []
        for target_name, weight in target_weights.items():
            allocated_amount = portfolio.total_equity * Decimal(str(weight))
            
            alloc = Allocation(
                portfolio_id=portfolio.id,
                target_type="strategy",
                target_name=target_name,
                weight=Decimal(str(weight)),
                allocated_amount=allocated_amount
            )
            self.db.add(alloc)
            
            old_w = previous_weights.get(target_name, 0.0)
            diff = weight - old_w
            execution_logs.append(f"Adjusted {target_name}: {old_w:.2%} -> {weight:.2%} (diff: {diff:+.2%})")

        # Create Rebalance Event
        event = RebalanceEvent(
            portfolio_id=portfolio.id,
            trigger_reason=trigger_reason,
            previous_weights=previous_weights,
            new_weights=target_weights,
            execution_log="\n".join(execution_logs),
            status=RebalanceStatus.completed
        )
        self.db.add(event)
        self.db.commit()

        return event
