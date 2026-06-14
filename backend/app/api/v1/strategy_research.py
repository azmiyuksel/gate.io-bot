from typing import List

import pandas as pd
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
    CustomHypothesisIn,
    ExperimentOut,
    FeatureRecordOut,
    GenerateIn,
    HypothesisTestOut,
    PromotionOut,
    ResearchStrategyOut,
    RunIn,
    RunOut,
    StrategyDetailOut,
    StrategyVersionOut,
    SymbolOut,
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


@router.get("/strategies/{strategy_id}/detail", response_model=StrategyDetailOut)
def strategy_detail(strategy_id: int, db: DbSession) -> dict:
    strategy = db.get(ResearchStrategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    versions = (
        db.query(StrategyVersion)
        .filter(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version.desc())
        .all()
    )
    trades_data: list[dict] = []
    equity_curve: list[dict] = []
    best_version = versions[0] if versions else None
    if best_version and best_version.metrics:
        trades_data = best_version.metrics.get("trades", [])
        equity_curve = best_version.metrics.get("equity_curve", [])

    return {
        "strategy": strategy,
        "versions": versions,
        "trades": trades_data,
        "equity_curve": equity_curve,
    }


@router.get("/symbols", response_model=list[SymbolOut])
def research_symbols(db: DbSession) -> list[dict]:
    from sqlalchemy import func
    from app.models.entities import HistoricalCandle

    symbols = (
        db.query(HistoricalCandle.symbol, func.count(HistoricalCandle.id))
        .group_by(HistoricalCandle.symbol)
        .having(func.count(HistoricalCandle.id) >= 100)
        .order_by(HistoricalCandle.symbol)
        .all()
    )
    return [{"symbol": s, "has_data": True} for s, _ in symbols]


@router.post("/hypotheses/custom", response_model=HypothesisTestOut, dependencies=[Depends(require_admin)])
def test_custom_hypothesis(payload: CustomHypothesisIn, db: DbSession) -> HypothesisTest:
    from app.strategy_research.hypothesis_builder import Hypothesis, HypothesisBuilder

    hypothesis = Hypothesis(
        statement=payload.statement,
        feature=payload.feature,
        condition_desc=payload.condition_desc,
        predicate=lambda f: pd.Series([True] * len(f), index=f.index),
    )
    builder = HypothesisBuilder(db)
    return builder.test(hypothesis, payload.symbol, payload.timeframe, bonferroni_n=1)
