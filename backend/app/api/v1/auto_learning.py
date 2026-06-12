from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import DbSession, current_user_role, require_admin
from app.auto_learning.engine import AutoLearningEngine
from app.auto_learning.models import PromotionRequestStatus
from app.models.entities import (
    DiscoveredFeature,
    HypothesisTest,
    KnowledgeEntry,
    LearningCycle,
    PromotionRequest,
    StrategyRanking,
)
from app.schemas._common import _validate_symbol, _validate_timeframe
from app.schemas.auto_learning import (
    DecisionIn,
    DiscoveredFeatureOut,
    HypothesisOut,
    KnowledgeEntryOut,
    LearningCycleOut,
    LearningRunIn,
    LearningRunOut,
    LearningStatusOut,
    PromotionRequestOut,
    StrategyRankingOut,
)

router = APIRouter(prefix="/learning", tags=["auto-learning"], dependencies=[Depends(current_user_role)])


@router.post("/start", response_model=LearningRunOut, dependencies=[Depends(require_admin)])
def start(payload: LearningRunIn, db: DbSession) -> LearningRunOut:
    summary = AutoLearningEngine(db).run_cycle(payload.symbol, payload.timeframe, payload.population)
    return LearningRunOut(**summary)


@router.post("/stop", dependencies=[Depends(require_admin)])
def stop(db: DbSession) -> dict:
    return AutoLearningEngine(db).stop()


@router.get("/status", response_model=LearningStatusOut)
def status(db: DbSession) -> LearningStatusOut:
    return LearningStatusOut(**AutoLearningEngine(db).status())


@router.get("/cycles", response_model=List[LearningCycleOut])
def cycles(db: DbSession, limit: int = 50) -> List[LearningCycle]:
    return (
        db.query(LearningCycle)
        .order_by(LearningCycle.started_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.get("/hypotheses", response_model=List[HypothesisOut])
def hypotheses(db: DbSession, limit: int = 50) -> List[HypothesisTest]:
    return (
        db.query(HypothesisTest)
        .order_by(HypothesisTest.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.get("/features", response_model=List[DiscoveredFeatureOut])
def features(
    db: DbSession,
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
) -> List[DiscoveredFeature]:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    return (
        db.query(DiscoveredFeature)
        .filter(DiscoveredFeature.symbol == symbol)
        .filter(DiscoveredFeature.timeframe == timeframe)
        .order_by(DiscoveredFeature.importance_score.desc())
        .all()
    )


@router.get("/rankings", response_model=List[StrategyRankingOut])
def rankings(db: DbSession, limit: int = 25) -> List[StrategyRanking]:
    return AutoLearningEngine(db).ranking.leaderboard(min(limit, 200))


@router.get("/knowledge", response_model=List[KnowledgeEntryOut])
def knowledge(db: DbSession, knowledge_type: str | None = None, limit: int = 100) -> List[KnowledgeEntry]:
    query = db.query(KnowledgeEntry)
    if knowledge_type:
        query = query.filter(KnowledgeEntry.knowledge_type == knowledge_type)
    return query.order_by(KnowledgeEntry.created_at.desc()).limit(min(limit, 500)).all()


@router.get("/promotion-requests", response_model=List[PromotionRequestOut])
def promotion_requests(db: DbSession, status: str | None = None, limit: int = 100) -> List[PromotionRequest]:
    query = db.query(PromotionRequest)
    if status:
        query = query.filter(PromotionRequest.status == status)
    return query.order_by(PromotionRequest.created_at.desc()).limit(min(limit, 500)).all()


@router.post(
    "/promote-request/{strategy_id}",
    response_model=PromotionRequestOut,
    dependencies=[Depends(require_admin)],
)
def approve_strategy_promotion(strategy_id: int, payload: DecisionIn, db: DbSession) -> PromotionRequest:
    """Human approval gate: approve the pending promotion request for a strategy."""
    request = (
        db.query(PromotionRequest)
        .filter(PromotionRequest.strategy_id == strategy_id)
        .filter(PromotionRequest.status == str(PromotionRequestStatus.awaiting_approval))
        .order_by(PromotionRequest.created_at.desc())
        .first()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="No promotion request awaiting approval for strategy")
    approved = AutoLearningEngine(db).approve_promotion(request.id, payload.decided_by, payload.note)
    if approved is None:
        raise HTTPException(status_code=409, detail="Request could not be approved")
    return approved


@router.post(
    "/promotion-requests/{request_id}/reject",
    response_model=PromotionRequestOut,
    dependencies=[Depends(require_admin)],
)
def reject_promotion(request_id: int, payload: DecisionIn, db: DbSession) -> PromotionRequest:
    rejected = AutoLearningEngine(db).reject_promotion(request_id, payload.decided_by, payload.note)
    if rejected is None:
        raise HTTPException(status_code=404, detail="No promotion request awaiting approval")
    return rejected


@router.post("/report", dependencies=[Depends(require_admin)])
def generate_report(db: DbSession, days: int = 7) -> dict:
    report = AutoLearningEngine(db).weekly_report(days)
    return {
        "id": report.id,
        "patterns_learned": report.patterns_learned,
        "failed_strategies": report.failed_strategies,
        "new_candidates": report.new_candidates,
        "promotion_requests": report.promotion_requests,
    }
