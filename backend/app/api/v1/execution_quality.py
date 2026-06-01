from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import (
    ExecutionOrder,
    ExecutionFill,
    ExecutionMetric,
    SlippageLog,
    LatencyLog,
    ExecutionReport,
    Trade,
)
from app.execution_quality.engine import ExecutionQualityEngine
from app.execution_quality.models import ExecutionQualityCategory
from app.schemas.execution_quality import (
    ExecutionQualityStatusOut,
    ExecutionSlippageOut,
    ExecutionLatencyOut,
    ExecutionReportOut,
)

router = APIRouter(prefix="/execution-quality", tags=["execution-quality"], dependencies=[Depends(current_user_role)])


@router.get("/{strategy_name}", response_model=ExecutionQualityStatusOut)
def get_strategy_execution_status(strategy_name: str, db: DbSession) -> dict:
    engine = ExecutionQualityEngine(db)
    
    # Fetch or compute latest metric
    metric = (
        db.query(ExecutionMetric)
        .filter(ExecutionMetric.strategy_name == strategy_name)
        .order_by(ExecutionMetric.timestamp.desc())
        .first()
    )
    if not metric:
        metric = engine.recalculate_metrics(strategy_name)

    # Detect anomalies
    is_anom, reason = engine.detect_anomalies(strategy_name)
    
    # Map score to category
    score = float(metric.execution_quality_score)
    if score >= 90.0:
        cat = ExecutionQualityCategory.excellent.value
    elif score >= 75.0:
        cat = ExecutionQualityCategory.good.value
    elif score >= 50.0:
        cat = ExecutionQualityCategory.acceptable.value
    else:
        cat = ExecutionQualityCategory.poor.value

    return {
        "strategy_name": strategy_name,
        "execution_quality_score": metric.execution_quality_score,
        "slippage_avg": metric.slippage_avg,
        "slippage_std": metric.slippage_std,
        "latency_total_execution_ms": metric.latency_total_execution_ms,
        "fill_completion_rate": metric.fill_completion_rate,
        "partial_fill_ratio": metric.partial_fill_ratio,
        "quality_category": cat,
        "anomaly_status": "ANOMALOUS" if is_anom else "NORMAL",
        "anomaly_reason": reason,
    }


@router.get("/slippage/logs", response_model=List[ExecutionSlippageOut])
def get_slippage_logs(
    db: DbSession,
    strategy_name: str = Query("capital_preservation_v1", description="Strategy Name"),
    limit: int = Query(100, ge=1, le=500)
) -> List[SlippageLog]:
    return (
        db.query(SlippageLog)
        .join(ExecutionOrder)
        .filter(ExecutionOrder.strategy_name == strategy_name)
        .order_by(SlippageLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/latency/logs", response_model=List[ExecutionLatencyOut])
def get_latency_logs(
    db: DbSession,
    strategy_name: str = Query("capital_preservation_v1", description="Strategy Name"),
    limit: int = Query(100, ge=1, le=500)
) -> List[LatencyLog]:
    return (
        db.query(LatencyLog)
        .join(ExecutionOrder)
        .filter(ExecutionOrder.strategy_name == strategy_name)
        .order_by(LatencyLog.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/report/logs", response_model=ExecutionReportOut)
def get_or_generate_report(
    db: DbSession,
    strategy_name: str = Query("capital_preservation_v1", description="Strategy Name"),
    days: int = Query(30, ge=1, le=365)
) -> ExecutionReport:
    engine = ExecutionQualityEngine(db)
    
    # Try to fetch recent report generated in the last 2 hours
    cutoff = datetime.now(UTC) - timedelta(hours=2)
    report = (
        db.query(ExecutionReport)
        .filter(
            ExecutionReport.strategy_name == strategy_name,
            ExecutionReport.created_at >= cutoff
        )
        .order_by(ExecutionReport.created_at.desc())
        .first()
    )
    
    if not report:
        # Generate new report
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(days=days)
        report = engine.generate_report(strategy_name, start_time, end_time)
        
    return report


@router.post("/recalculate", response_model=ExecutionQualityStatusOut, dependencies=[Depends(require_admin)])
def recalculate_quality(
    db: DbSession,
    strategy_name: str = Query("capital_preservation_v1", description="Strategy Name")
) -> dict:
    engine = ExecutionQualityEngine(db)
    
    # Recalculate metrics based on current DB orders and fills
    engine.recalculate_metrics(strategy_name)
    
    return get_strategy_execution_status(strategy_name, db)
