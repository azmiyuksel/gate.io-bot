from decimal import Decimal
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import DbSession, current_user_role, require_admin
from app.core.config import get_settings
from app.models.entities import Allocation, Portfolio, PortfolioAsset, PortfolioMetric, RebalanceEvent, RiskSnapshot
from app.models.enums import RebalanceTrigger
from app.portfolio.correlation import CorrelationEngine
from app.portfolio.engine import PortfolioEngine
from app.portfolio.models import DEFAULT_STRATEGY_WEIGHTS
from app.portfolio.risk_model import PortfolioRiskModel
from app.schemas.portfolio import (
    AllocationOut,
    PortfolioCreate,
    PortfolioMetricOut,
    PortfolioOut,
    RebalanceOut,
    RiskSnapshotOut,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"], dependencies=[Depends(current_user_role)])


@router.post("/create", response_model=PortfolioOut, dependencies=[Depends(require_admin)])
def create_portfolio(payload: PortfolioCreate, db: DbSession) -> Portfolio:
    existing = db.query(Portfolio).filter(Portfolio.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Portfolio already exists")

    portfolio = Portfolio(
        name=payload.name,
        description=payload.description,
        total_equity=payload.initial_balance,
        cash_balance=payload.initial_balance,
        daily_max_risk_pct=payload.daily_max_risk_pct,
        weekly_max_risk_pct=payload.weekly_max_risk_pct,
        monthly_max_risk_pct=payload.monthly_max_risk_pct,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    # Initialize default weights
    from app.portfolio.models import DEFAULT_STRATEGY_WEIGHTS
    for target, weight in DEFAULT_STRATEGY_WEIGHTS.items():
        alloc = Allocation(
            portfolio_id=portfolio.id,
            target_type="strategy",
            target_name=target,
            weight=weight,
            allocated_amount=payload.initial_balance * weight
        )
        db.add(alloc)
    db.commit()
    db.refresh(portfolio)

    # Record initial metrics
    engine = PortfolioEngine(db, portfolio)
    engine.record_metrics()

    return portfolio


@router.get("", response_model=PortfolioOut)
def get_portfolio(db: DbSession) -> Portfolio:
    return _get_or_create_portfolio(db)


@router.get("/metrics", response_model=List[PortfolioMetricOut])
def get_metrics(db: DbSession) -> List[PortfolioMetric]:
    portfolio = _get_or_create_portfolio(db)
    return (
        db.query(PortfolioMetric)
        .filter(PortfolioMetric.portfolio_id == portfolio.id)
        .order_by(PortfolioMetric.timestamp.asc())
        .limit(1000)
        .all()
    )


@router.get("/allocations", response_model=List[AllocationOut])
def get_allocations(db: DbSession) -> List[Allocation]:
    portfolio = _get_or_create_portfolio(db)
    return (
        db.query(Allocation)
        .filter(Allocation.portfolio_id == portfolio.id)
        .all()
    )


@router.post("/rebalance", dependencies=[Depends(require_admin)])
def trigger_rebalance(db: DbSession) -> dict:
    portfolio = _get_or_create_portfolio(db)
    engine = PortfolioEngine(db, portfolio)
    
    # Simulate fetching active spot positions from the Paper Trading position table (if running paper bot)
    # or keep default assets.
    # To keep it generic and functional, we update engine positions first.
    from app.models.entities import PaperPosition
    paper_positions = db.query(PaperPosition).filter(PaperPosition.is_open.is_(True)).all()
    active_pos = []
    for p in paper_positions:
        active_pos.append({
            "symbol": p.symbol,
            "quantity": float(p.quantity),
            "entry_price": float(p.average_entry_price),
            "last_price": float(p.last_price)
        })
    
    engine.update_positions(active_pos)
    engine.rebalance(trigger_reason=RebalanceTrigger.manual)
    
    return {"status": "rebalanced", "portfolio_id": portfolio.id}


@router.post("/reset", dependencies=[Depends(require_admin)])
def reset_portfolio(db: DbSession) -> dict:
    portfolio = _get_or_create_portfolio(db)
    db.query(PortfolioMetric).filter(PortfolioMetric.portfolio_id == portfolio.id).delete()
    db.query(RebalanceEvent).filter(RebalanceEvent.portfolio_id == portfolio.id).delete()
    db.query(RiskSnapshot).filter(RiskSnapshot.portfolio_id == portfolio.id).delete()
    db.query(PortfolioAsset).filter(PortfolioAsset.portfolio_id == portfolio.id).delete()
    
    # Re-initialize allocations
    db.query(Allocation).filter(Allocation.portfolio_id == portfolio.id).delete()
    from app.portfolio.models import DEFAULT_STRATEGY_WEIGHTS
    for target, weight in DEFAULT_STRATEGY_WEIGHTS.items():
        alloc = Allocation(
            portfolio_id=portfolio.id,
            target_type="strategy",
            target_name=target,
            weight=weight,
            allocated_amount=portfolio.cash_balance * weight
        )
        db.add(alloc)

    portfolio.total_equity = portfolio.cash_balance
    db.commit()

    # Log initial metric
    engine = PortfolioEngine(db, portfolio)
    engine.record_metrics()

    return {"status": "reset", "portfolio_id": portfolio.id}


@router.post("/stress-test", response_model=RiskSnapshotOut, dependencies=[Depends(require_admin)])
def trigger_stress_test(scenario_name: str, db: DbSession) -> RiskSnapshot:
    portfolio = _get_or_create_portfolio(db)
    engine = PortfolioEngine(db, portfolio)
    snapshot = engine.run_stress_testing(scenario_name)
    return snapshot


@router.get("/rebalances", response_model=List[RebalanceOut])
def get_rebalance_history(db: DbSession) -> List[RebalanceEvent]:
    portfolio = _get_or_create_portfolio(db)
    return (
        db.query(RebalanceEvent)
        .filter(RebalanceEvent.portfolio_id == portfolio.id)
        .order_by(RebalanceEvent.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/correlations")
def get_correlations(db: DbSession) -> dict:
    """Live return-correlation matrix for the configured universe, computed from
    cached historical candles. Replaces the dashboard's previously hardcoded
    matrix; `data_available` is False when there isn't enough history yet."""
    settings = get_settings()
    timeframe = settings.market_data_interval
    result = CorrelationEngine(db).calculate_correlation(settings.symbols, timeframe)
    # The engine only populates volatilities/covariance when it had real returns;
    # otherwise it returns a placeholder matrix we must not present as real data.
    data_available = "volatilities" in result
    matrix = result.get("matrix", {}) if data_available else {}
    return {
        "symbols": list(matrix.keys()),
        "matrix": matrix,
        "high_correlation_pairs": result.get("high_correlation_pairs", []),
        "risk_score": result.get("risk_score", 0.0),
        "timeframe": timeframe,
        "data_available": data_available,
    }


@router.get("/risk-check")
def check_portfolio_risk(db: DbSession) -> dict:
    portfolio = _get_or_create_portfolio(db)
    passed, reason = PortfolioRiskModel(db).check_risk_limits(portfolio)
    engine = PortfolioEngine(db, portfolio)
    var_cvar = engine.value_at_risk()
    return {"passed": passed, "reason": reason, "var_95": var_cvar["var"], "cvar_95": var_cvar["cvar"]}


@router.get("/var")
def get_portfolio_var(db: DbSession) -> dict:
    portfolio = _get_or_create_portfolio(db)
    engine = PortfolioEngine(db, portfolio)
    return engine.value_at_risk()


@router.delete("/{portfolio_id}", dependencies=[Depends(require_admin)])
def delete_portfolio(portfolio_id: int, db: DbSession) -> dict:
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    db.delete(portfolio)
    db.commit()
    return {"status": "deleted", "portfolio_id": portfolio_id}


@router.get("/strategy-performance")
def get_strategy_performance(db: DbSession) -> list[dict]:
    portfolio = _get_or_create_portfolio(db)
    engine = PortfolioEngine(db, portfolio)
    result = []
    for name in DEFAULT_STRATEGY_WEIGHTS:
        perf = engine._compute_strategy_performance(name)
        result.append({
            "name": name,
            "sharpe_ratio": float(perf.sharpe_ratio),
            "win_rate": float(perf.win_rate),
            "profit_factor": float(perf.profit_factor),
            "max_drawdown": float(perf.max_drawdown),
            "stability_score": float(perf.stability_score),
        })
    return result


def _get_or_create_portfolio(db: DbSession, name: str = "default", initial_balance: Decimal = Decimal("10000")) -> Portfolio:
    portfolio = db.query(Portfolio).filter(Portfolio.name == name).first()
    if portfolio is None:
        portfolio = Portfolio(
            name=name,
            total_equity=initial_balance,
            cash_balance=initial_balance,
            daily_max_risk_pct=Decimal("0.02"),
            weekly_max_risk_pct=Decimal("0.05"),
            monthly_max_risk_pct=Decimal("0.10"),
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)

        # Initialize default weights
        from app.portfolio.models import DEFAULT_STRATEGY_WEIGHTS
        for target, weight in DEFAULT_STRATEGY_WEIGHTS.items():
            alloc = Allocation(
                portfolio_id=portfolio.id,
                target_type="strategy",
                target_name=target,
                weight=weight,
                allocated_amount=initial_balance * weight
            )
            db.add(alloc)
        db.commit()
        db.refresh(portfolio)
        
        # Record initial metrics
        engine = PortfolioEngine(db, portfolio)
        engine.record_metrics()

    return portfolio
