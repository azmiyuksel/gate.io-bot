from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import (
    ABTestResult,
    FeatureRecord,
    HypothesisTest,
    ResearchExperiment,
    ResearchStrategy,
    StrategyVersion,
)
from app.schemas._common import _validate_symbol, _validate_timeframe
from app.schemas.strategy_research import (
    ABTestOut,
    ExperimentOut,
    FeatureRecordOut,
    GenerateIn,
    HypothesisTestOut,
    PromotionOut,
    ResearchStrategyOut,
    RunIn,
    RunOut,
    StrategyVersionOut,
)
from app.strategy_research.engine import StrategyResearchEngine
from app.strategy_research.feature_store import FeatureStore
from app.strategy_research.hypothesis_builder import HypothesisBuilder

router = APIRouter(
    prefix="/research", tags=["strategy-research"], dependencies=[Depends(current_user_role)]
)


@router.post("/generate", dependencies=[Depends(require_admin)])
def generate(payload: GenerateIn, db: DbSession) -> dict:
    engine = StrategyResearchEngine(db)
    genome = engine.generate_strategy(
        template=payload.template,
        feature_driven=payload.feature_driven,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
    )
    if not payload.evaluate:
        return {"template": genome.template, "parameters": genome.parameters, "origin": genome.origin}

    outcome = engine.evaluate_strategy(genome, payload.symbol, payload.timeframe)
    if outcome is None:
        raise HTTPException(status_code=422, detail="Insufficient historical data to evaluate")
    strategy, version, result = outcome
    return {
        "strategy_id": strategy.id,
        "version_id": version.id,
        "fitness": round(result.fitness, 6),
        "sharpe": round(result.sharpe, 6),
        "overfit": result.overfit,
        "parameters": genome.parameters,
    }


@router.post("/run", response_model=RunOut, dependencies=[Depends(require_admin)])
def run(payload: RunIn, db: DbSession) -> RunOut:
    engine = StrategyResearchEngine(db)
    summary = engine.run_experiments(payload.symbol, payload.timeframe, payload.population)
    return RunOut(**{**{"best_strategy_id": None, "best_sharpe": None, "reason": None}, **summary})


@router.get("/strategies", response_model=List[ResearchStrategyOut])
def strategies(db: DbSession, status: str | None = None, limit: int = 100) -> List[ResearchStrategy]:
    query = db.query(ResearchStrategy)
    if status:
        query = query.filter(ResearchStrategy.status == status)
    return query.order_by(ResearchStrategy.best_fitness.desc()).limit(min(limit, 500)).all()


@router.get("/leaderboard", response_model=List[StrategyVersionOut])
def leaderboard(db: DbSession, limit: int = 25) -> List[StrategyVersion]:
    return StrategyResearchEngine(db).rank_strategies(min(limit, 200))


@router.get("/experiments", response_model=List[ExperimentOut])
def experiments(db: DbSession, limit: int = 100) -> List[ResearchExperiment]:
    return (
        db.query(ResearchExperiment)
        .order_by(ResearchExperiment.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )


@router.get("/features", response_model=List[FeatureRecordOut])
def features(
    db: DbSession,
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
) -> List[FeatureRecord]:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    return (
        db.query(FeatureRecord)
        .filter(FeatureRecord.symbol == symbol)
        .filter(FeatureRecord.timeframe == timeframe)
        .order_by(FeatureRecord.importance_score.desc())
        .all()
    )


@router.post("/features/recompute", response_model=List[FeatureRecordOut],
             dependencies=[Depends(require_admin)])
def recompute_features(
    db: DbSession,
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
) -> List[FeatureRecord]:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    FeatureStore(db).compute(symbol, timeframe)
    return (
        db.query(FeatureRecord)
        .filter(FeatureRecord.symbol == symbol)
        .filter(FeatureRecord.timeframe == timeframe)
        .order_by(FeatureRecord.importance_score.desc())
        .all()
    )


@router.get("/hypotheses", response_model=List[HypothesisTestOut])
def hypotheses(db: DbSession, limit: int = 50) -> List[HypothesisTest]:
    return (
        db.query(HypothesisTest)
        .order_by(HypothesisTest.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.post("/hypotheses/test", response_model=List[HypothesisTestOut],
             dependencies=[Depends(require_admin)])
def test_hypotheses(
    db: DbSession,
    symbol: str = Query("BTC_USDT"),
    timeframe: str = Query("1h"),
) -> List[HypothesisTest]:
    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    return HypothesisBuilder(db).test_all(symbol, timeframe)


@router.get("/ab-tests", response_model=List[ABTestOut])
def ab_tests(db: DbSession, limit: int = 50) -> List[ABTestResult]:
    return (
        db.query(ABTestResult)
        .order_by(ABTestResult.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.post("/promote/{strategy_id}", response_model=PromotionOut, dependencies=[Depends(require_admin)])
def promote(strategy_id: int, db: DbSession) -> PromotionOut:
    verdict = StrategyResearchEngine(db).promote_to_production(strategy_id)
    return PromotionOut(
        strategy_id=strategy_id,
        decision=str(verdict.decision),
        passed=verdict.passed,
        reasons=verdict.reasons,
    )
