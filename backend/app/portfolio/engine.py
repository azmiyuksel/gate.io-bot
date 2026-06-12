import logging
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict, List, Any
from sqlalchemy.orm import Session

from app.core.config import get_settings as _get_settings
from app.models.entities import (
    Allocation,
    Portfolio,
    PortfolioAsset,
    PortfolioMetric,
    RiskSnapshot,
    Trade,
)
from app.models.enums import PositionStatus, RebalanceTrigger
from app.portfolio.allocator import CapitalAllocator
from app.portfolio.correlation import CorrelationEngine
from app.portfolio.exposure import ExposureManager
from app.portfolio.models import DEFAULT_STRATEGY_WEIGHTS, StrategyPerformance
from app.portfolio.optimizer import PortfolioOptimizer
from app.portfolio.rebalancer import PortfolioRebalancer
from app.portfolio.risk_model import PortfolioRiskModel

logger = logging.getLogger(__name__)

_MAJORS = {"BTC_USDT", "ETH_USDT", "BTC", "ETH", "BTC_USD", "ETH_USD"}


def _scenario_shocks(scenario: str, symbols: list[str]) -> tuple[dict[str, float], str]:
    """Per-symbol price shock (fraction) for a stress scenario."""
    s = _get_settings()
    if scenario == "market_crash_30":
        return {sym: -s.stress_market_crash_pct for sym in symbols}, scenario
    if scenario == "flash_crash":
        return {sym: (-s.stress_flash_crash_major if sym in _MAJORS else -s.stress_flash_crash_alt) for sym in symbols}, scenario
    if scenario == "high_volatility":
        return {sym: -s.stress_high_vol_pct for sym in symbols}, scenario
    if scenario == "correlation_spike":
        return {sym: -s.stress_correlation_spike_pct for sym in symbols}, scenario
    return {sym: 0.0 for sym in symbols}, "custom_scenario"


class PortfolioEngine:
    def __init__(self, db: Session, portfolio: Portfolio) -> None:
        self.db = db
        self.portfolio = portfolio
        self.risk_model = PortfolioRiskModel(db)
        self.correlation_engine = CorrelationEngine(db)
        self.rebalancer = PortfolioRebalancer(db)
        self.allocator = CapitalAllocator()

    def update_market_data(self, prices: Dict[str, Decimal]) -> None:
        """
        Updates current prices of active assets.
        """
        assets = self.db.query(PortfolioAsset).filter(PortfolioAsset.portfolio_id == self.portfolio.id).all()
        for asset in assets:
            if asset.symbol in prices:
                asset.current_price = prices[asset.symbol]
                # Update unrealized PnL
                if asset.position_size > 0:
                    asset.unrealized_pnl = (asset.current_price - asset.average_entry_price) * asset.position_size
                else:
                    asset.unrealized_pnl = Decimal("0")
                asset.updated_at = datetime.now(UTC)
        self.db.commit()

    def update_positions(self, active_positions: List[Dict[str, Any]]) -> None:
        """
        Syncs open positions to the PortfolioAsset table.
        Merges with existing assets to preserve metadata from other sources.
        """
        existing = {
            a.symbol: a
            for a in self.db.query(PortfolioAsset)
            .filter(PortfolioAsset.portfolio_id == self.portfolio.id)
            .all()
        }
        seen_symbols = set()

        for pos in active_positions:
            symbol = pos["symbol"]
            qty = Decimal(str(pos["quantity"]))
            entry = Decimal(str(pos["entry_price"]))
            curr = Decimal(str(pos.get("last_price", pos["entry_price"])))
            pnl = (curr - entry) * qty
            seen_symbols.add(symbol)

            if symbol in existing:
                asset = existing[symbol]
                asset.position_size = qty
                asset.average_entry_price = entry
                asset.current_price = curr
                asset.unrealized_pnl = pnl
                asset.updated_at = datetime.now(UTC)
            else:
                asset = PortfolioAsset(
                    portfolio_id=self.portfolio.id,
                    symbol=symbol,
                    position_size=qty,
                    average_entry_price=entry,
                    current_price=curr,
                    unrealized_pnl=pnl,
                    risk_contribution=Decimal("0.0"),
                )
                self.db.add(asset)

        # Zero out assets for symbols that are no longer open
        for symbol, asset in existing.items():
            if symbol not in seen_symbols:
                asset.position_size = Decimal("0")
                asset.unrealized_pnl = Decimal("0")
                asset.updated_at = datetime.now(UTC)

        self.db.commit()
        self.calculate_equity()

    def calculate_equity(self) -> Decimal:
        """
        Recalculates total equity: cash_balance + sum of position values.
        Updates peak_equity when a new high is reached.
        """
        assets = self.db.query(PortfolioAsset).filter(PortfolioAsset.portfolio_id == self.portfolio.id).all()
        position_value = sum((a.position_size * a.current_price for a in assets), Decimal("0"))
        self.portfolio.total_equity = self.portfolio.cash_balance + position_value
        # Track peak equity for drawdown calculation
        if self.portfolio.total_equity > self.portfolio.peak_equity:
            self.portfolio.peak_equity = self.portfolio.total_equity
        self.portfolio.updated_at = datetime.now(UTC)
        self.db.commit()
        return self.portfolio.total_equity

    def _compute_strategy_performance(self, name: str) -> StrategyPerformance:
        """Compute real performance metrics from closed trades in the database."""
        trades = (
            self.db.query(Trade)
            .filter(Trade.status == PositionStatus.closed)
            .filter(Trade.strategy_name == name)
            .order_by(Trade.closed_at.desc())
            .limit(500)
            .all()
        )
        pnls = [float(t.realized_pnl) for t in trades if t.realized_pnl is not None]
        if not pnls:
            return StrategyPerformance(name=name)

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = Decimal(str(len(wins) / len(pnls))) if pnls else Decimal("0")
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        profit_factor = Decimal(str((avg_win * len(wins)) / (avg_loss * len(losses)))) if losses and avg_loss > 0 else Decimal("1.0")

        # Rolling Sharpe from equity-equivalent PnL series
        import numpy as np
        arr = np.array(pnls[::-1], dtype="float64")
        std = float(arr.std()) if len(arr) > 1 else 0.0
        sharpe = Decimal(str(float(arr.mean()) / std * (365 ** 0.5))) if std > 0 else Decimal("0")

        # Max drawdown from cumulative PnL
        cum = np.cumsum(arr)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dd = Decimal(str(float(dd.max() / (peak.max() + 1e-9)))) if len(dd) else Decimal("0")

        # Stability: fraction of sign-consistent chunks
        n = len(pnls)
        chunk_size = max(n // 4, 1)
        signs = []
        for i in range(4):
            chunk = pnls[i * chunk_size:(i + 1) * chunk_size]
            if chunk:
                signs.append(1 if sum(chunk) > 0 else -1)
        stability = Decimal(str(max(signs.count(1), signs.count(-1)) / len(signs))) if signs else Decimal("0.5")

        return StrategyPerformance(
            name=name,
            sharpe_ratio=sharpe,
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            stability_score=stability,
        )

    def allocate_capital(self) -> Dict[str, Decimal]:
        """
        Allocates capital across strategies using the Capital Allocator.
        """
        # Fetch current correlation matrix
        assets = self.db.query(PortfolioAsset).filter(PortfolioAsset.portfolio_id == self.portfolio.id).all()
        symbols = [a.symbol for a in assets]
        corr_data = self.correlation_engine.calculate_correlation(symbols)

        strategies = []
        drawdowns = {}
        for name in DEFAULT_STRATEGY_WEIGHTS:
            perf = self._compute_strategy_performance(name)
            strategies.append({
                "name": name,
                "sharpe_ratio": float(perf.sharpe_ratio),
                "win_rate": float(perf.win_rate),
                "profit_factor": float(perf.profit_factor),
                "stability_score": float(perf.stability_score),
            })
            drawdowns[name] = perf.max_drawdown

        allocations = self.allocator.allocate_capital(
            self.portfolio.total_equity,
            strategies,
            corr_data["matrix"],
            drawdowns
        )

        return allocations

    def rebalance(self, trigger_reason: RebalanceTrigger = RebalanceTrigger.manual) -> None:
        """
        Forces capital rebalancing across strategies.
        """
        allocations = self.allocate_capital()
        total_alloc = sum(allocations.values()) if allocations else Decimal("1")
        target_weights = {name: float(amount / total_alloc) for name, amount in allocations.items()}

        self.rebalancer.execute_rebalance(
            self.portfolio,
            target_weights,
            trigger_reason
        )
        self.record_metrics()

    def record_metrics(self) -> PortfolioMetric:
        """
        Calculates and records a snapshot of portfolio metrics.
        """
        self.calculate_equity()
        
        # 1. Gather assets
        assets = self.db.query(PortfolioAsset).filter(PortfolioAsset.portfolio_id == self.portfolio.id).all()
        symbols = [a.symbol for a in assets]
        
        # 2. Correlation risk score
        corr_data = self.correlation_engine.calculate_correlation(symbols)
        corr_score = Decimal(str(corr_data["risk_score"]))

        # 3. Calculate Exposures
        allocs = self.db.query(Allocation).filter(Allocation.portfolio_id == self.portfolio.id).all()
        asset_exps = ExposureManager.calculate_asset_exposures(assets, self.portfolio.total_equity)
        strat_exps = ExposureManager.calculate_strategy_exposures(allocs, asset_exps)

        # 4. Drawdown
        drawdown_pct = Decimal("0")
        if self.portfolio.peak_equity > 0 and self.portfolio.total_equity < self.portfolio.peak_equity:
            drawdown_pct = (self.portfolio.peak_equity - self.portfolio.total_equity) / self.portfolio.peak_equity

        # 5. Compute portfolio-level Sharpe from recorded equity history
        sharpe_ratio = self._compute_portfolio_sharpe()

        # 6. Compute volatility-adjusted return (annualized return / annualized vol)
        vol_adj_return = self._compute_volatility_adjusted_return()

        metric = PortfolioMetric(
            portfolio_id=self.portfolio.id,
            timestamp=datetime.now(UTC),
            total_equity=self.portfolio.total_equity,
            sharpe_ratio=sharpe_ratio,
            drawdown=drawdown_pct,
            correlation_risk_score=corr_score,
            exposure_per_asset=asset_exps,
            exposure_per_strategy=strat_exps,
            volatility_adjusted_return=vol_adj_return,
        )
        self.db.add(metric)
        self.db.commit()
        return metric

    def _compute_portfolio_sharpe(self) -> Decimal:
        """Compute Sharpe ratio from the equity history stored in PortfolioMetric."""
        import numpy as np

        rows = (
            self.db.query(PortfolioMetric)
            .filter(PortfolioMetric.portfolio_id == self.portfolio.id)
            .order_by(PortfolioMetric.timestamp.asc())
            .limit(500)
            .all()
        )
        equities = [float(r.total_equity) for r in rows if r.total_equity]
        if len(equities) < 3:
            return Decimal("0")
        arr = np.array(equities, dtype="float64")
        returns = np.diff(arr) / arr[:-1]
        returns = returns[np.isfinite(returns)]
        if returns.size == 0:
            return Decimal("0")
        std = float(returns.std())
        if std <= 0:
            return Decimal("0")
        # Annualize assuming hourly returns (24 * 365)
        sharpe = float(returns.mean()) / std * math.sqrt(24 * 365)
        return Decimal(str(round(sharpe, 4)))

    def _compute_volatility_adjusted_return(self) -> Decimal:
        """Annualized return / annualized volatility from equity history."""
        import numpy as np

        rows = (
            self.db.query(PortfolioMetric)
            .filter(PortfolioMetric.portfolio_id == self.portfolio.id)
            .order_by(PortfolioMetric.timestamp.asc())
            .limit(500)
            .all()
        )
        equities = [float(r.total_equity) for r in rows if r.total_equity]
        if len(equities) < 3:
            return Decimal("0")
        arr = np.array(equities, dtype="float64")
        returns = np.diff(arr) / arr[:-1]
        returns = returns[np.isfinite(returns)]
        if returns.size == 0:
            return Decimal("0")
        ann_return = float(returns.mean()) * 24 * 365
        ann_vol = float(returns.std()) * math.sqrt(24 * 365)
        if ann_vol <= 0:
            return Decimal("0")
        return Decimal(str(round(ann_return / ann_vol, 4)))

    def run_stress_testing(self, scenario_name: str) -> RiskSnapshot:
        """
        Stress test by SHOCKING ACTUAL HOLDINGS, not a flat haircut on equity.

        Each scenario applies a per-asset price shock to the real positions, so
        the loss depends on actual exposure: a mostly-cash portfolio barely moves
        while a fully-invested one takes the full hit.
        """
        assets = (
            self.db.query(PortfolioAsset)
            .filter(PortfolioAsset.portfolio_id == self.portfolio.id)
            .all()
        )
        cash = float(self.portfolio.cash_balance)
        position_value = float(sum((a.position_size * a.current_price for a in assets), Decimal("0")))
        equity_before = cash + position_value

        shocks, scenario_name = _scenario_shocks(scenario_name, [a.symbol for a in assets])
        shocked_value = 0.0
        per_asset: dict[str, float] = {}
        for asset in assets:
            base = float(asset.position_size * asset.current_price)
            shock = shocks.get(asset.symbol, 0.0)
            shocked_value += base * (1 + shock)
            per_asset[asset.symbol] = base * shock  # signed loss contribution
        equity_after = cash + shocked_value
        loss = equity_before - equity_after
        loss_pct = loss / equity_before if equity_before > 0 else 0.0

        status = "violated" if loss_pct > float(self.portfolio.daily_max_risk_pct) else "normal"
        var_cvar = self.value_at_risk()

        snapshot = RiskSnapshot(
            portfolio_id=self.portfolio.id,
            timestamp=datetime.now(UTC),
            scenario_name=scenario_name,
            simulated_loss=Decimal(str(loss)),
            limit_status=status,
            metrics_snapshot={
                "equity_before": equity_before,
                "equity_after": equity_after,
                "simulated_loss_pct": loss_pct,
                "position_value": position_value,
                "per_asset_loss": per_asset,
                "historical_var_95": var_cvar["var"],
                "historical_cvar_95": var_cvar["cvar"],
            },
        )
        self.db.add(snapshot)
        self.db.commit()
        return snapshot

    def risk_parity_allocation(self) -> Dict[str, float]:
        """Equal-risk-contribution weights across held assets, from the real
        return covariance (a genuine optimization, not a heuristic score)."""
        assets = (
            self.db.query(PortfolioAsset)
            .filter(PortfolioAsset.portfolio_id == self.portfolio.id)
            .all()
        )
        symbols = [a.symbol for a in assets]
        if not symbols:
            return {}
        corr_data = self.correlation_engine.calculate_correlation(symbols)
        covariance = corr_data.get("covariance", {})
        if not covariance:
            return {s: 1.0 / len(symbols) for s in symbols}
        return PortfolioOptimizer.risk_parity_weights(covariance)

    def value_at_risk(self, confidence: float = 0.95, lookback: int | None = None) -> dict:
        """Historical VaR/CVaR from the recorded portfolio-equity history.

        *lookback* defaults to the ``var_lookback`` setting (default 500 bars).
        """
        if lookback is None:
            lookback = _get_settings().var_lookback
        rows = (
            self.db.query(PortfolioMetric)
            .filter(PortfolioMetric.portfolio_id == self.portfolio.id)
            .order_by(PortfolioMetric.timestamp.desc())
            .limit(lookback)
            .all()
        )
        equities = [float(r.total_equity) for r in reversed(rows) if r.total_equity]
        return PortfolioRiskModel.historical_var_cvar(equities, confidence)
