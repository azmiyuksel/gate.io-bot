from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import (
    StrategyAlert,
    StrategyBaseline,
    StrategyHealthLog,
    StrategySettings,
    StrategyStateHistory,
    Trade,
)
from app.models.enums import StrategyHealthState
from app.strategy_health.engine import StrategyHealthEngine
from app.schemas.health import (
    StrategyAlertOut,
    StrategyBaselineOut,
    StrategyHealthLogOut,
    StrategyHealthOut,
    StrategyStateHistoryOut,
)

router = APIRouter(prefix="/strategy-health", tags=["strategy-health"], dependencies=[Depends(current_user_role)])


@router.get("/{strategy_name}", response_model=StrategyHealthOut)
def get_strategy_health(strategy_name: str, db: DbSession) -> dict:
    # Warm up health engine and compute health scores
    engine = StrategyHealthEngine(db)
    result = engine.update_health(strategy_name)
    return result


@router.get("/{strategy_name}/metrics", response_model=List[StrategyHealthLogOut])
def get_health_metrics(strategy_name: str, db: DbSession) -> List[StrategyHealthLog]:
    return (
        db.query(StrategyHealthLog)
        .filter(StrategyHealthLog.strategy_name == strategy_name)
        .order_by(StrategyHealthLog.created_at.asc())
        .limit(500)
        .all()
    )


@router.get("/{strategy_name}/alerts", response_model=List[StrategyAlertOut])
def get_strategy_alerts(strategy_name: str, db: DbSession) -> List[StrategyAlert]:
    return (
        db.query(StrategyAlert)
        .filter(StrategyAlert.strategy_name == strategy_name)
        .order_by(StrategyAlert.created_at.desc())
        .limit(100)
        .all()
    )


@router.post("/{strategy_name}/recalculate", response_model=StrategyHealthOut, dependencies=[Depends(require_admin)])
def recalculate_strategy_health(strategy_name: str, db: DbSession) -> dict:
    engine = StrategyHealthEngine(db)
    
    # Recalculate based on existing trades
    trades = db.query(Trade).order_by(Trade.traded_at.asc()).all()
    
    # Run historical sequence simulation
    result = {}
    for i in range(5, len(trades) + 1):
        sub_trades = trades[:i]
        result = engine.update_health(strategy_name, sub_trades)
        
    if not result:
        result = engine.update_health(strategy_name)
        
    return result


@router.post("/{strategy_name}/pause", dependencies=[Depends(require_admin)])
def pause_strategy(strategy_name: str, db: DbSession) -> dict:
    settings = db.query(StrategySettings).filter(StrategySettings.name == strategy_name).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Strategy settings not found")
        
    settings.is_enabled = False
    
    # Log state transition
    transition = StrategyStateHistory(
        strategy_name=strategy_name,
        old_state=StrategyHealthState.active,
        new_state=StrategyHealthState.paused,
        trigger_reason="Manually paused via Health API"
    )
    db.add(transition)
    db.commit()
    
    return {"status": "paused", "strategy": strategy_name}


@router.post("/{strategy_name}/resume", dependencies=[Depends(require_admin)])
def resume_strategy(strategy_name: str, db: DbSession) -> dict:
    settings = db.query(StrategySettings).filter(StrategySettings.name == strategy_name).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Strategy settings not found")
        
    settings.is_enabled = True
    
    # Log state transition
    transition = StrategyStateHistory(
        strategy_name=strategy_name,
        old_state=StrategyHealthState.paused,
        new_state=StrategyHealthState.active,
        trigger_reason="Manually resumed via Health API"
    )
    db.add(transition)
    db.commit()
    
    return {"status": "resumed", "strategy": strategy_name}


@router.get("/{strategy_name}/baseline", response_model=StrategyBaselineOut)
def get_strategy_baseline(strategy_name: str, db: DbSession) -> StrategyBaseline:
    from app.strategy_health.baseline import StrategyBaselineManager
    manager = StrategyBaselineManager(db)
    return manager.get_or_create_baseline(strategy_name)


@router.get("/{strategy_name}/transitions", response_model=List[StrategyStateHistoryOut])
def get_transitions(strategy_name: str, db: DbSession) -> List[StrategyStateHistory]:
    return (
        db.query(StrategyStateHistory)
        .filter(StrategyStateHistory.strategy_name == strategy_name)
        .order_by(StrategyStateHistory.created_at.desc())
        .limit(50)
        .all()
    )
