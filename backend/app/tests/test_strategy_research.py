import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.entities import (
    HistoricalCandle,
    ResearchStrategy,
    StrategyVersion,
)
from app.strategy_research.evaluator import StrategyEvaluator
from app.strategy_research.engine import StrategyResearchEngine
from app.strategy_research.feature_store import FeatureStore
from app.strategy_research.generator import TEMPLATE_SEED_PARAMETERS, StrategyGenerator
from app.strategy_research.hypothesis_builder import HypothesisBuilder
from app.strategy_research.models import (
    EvaluationResult,
    StrategyGenome,
    compute_fitness,
    get_template,
)
from app.strategy_research.repository import ResearchRepository


# --------------------------------------------------------------------------
# Test data: synthetic OHLCV with mild uptrend + noise
# --------------------------------------------------------------------------
def seed_candles(db, symbol="BTC_USDT", timeframe="1h", n=700, seed=11) -> None:
    import random

    rng = random.Random(seed)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    price = 100.0
    for i in range(n):
        drift = 0.0005
        price *= 1 + drift + rng.uniform(-0.01, 0.01)
        high = price * (1 + abs(rng.uniform(0, 0.006)))
        low = price * (1 - abs(rng.uniform(0, 0.006)))
        opn = price * (1 + rng.uniform(-0.003, 0.003))
        db.add(
            HistoricalCandle(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=Decimal(str(round(opn, 4))),
                high=Decimal(str(round(max(high, opn, price), 4))),
                low=Decimal(str(round(min(low, opn, price), 4))),
                close=Decimal(str(round(price, 4))),
                volume=Decimal(str(round(rng.uniform(50, 150), 4))),
                source="test",
            )
        )
    db.commit()


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------
def test_generator_samples_within_bounds() -> None:
    gen = StrategyGenerator(seed=1)
    genome = gen.generate("ema_rsi_atr", 1)[0]
    template = get_template("ema_rsi_atr")
    for spec in template.params:
        value = genome.parameters[spec.name]
        assert spec.low <= value <= spec.high


def test_seed_genome_matches_seed_parameters() -> None:
    gen = StrategyGenerator(seed=1)
    genome = gen.seed_genome()
    assert genome.origin == "seed"
    assert genome.parameters["ema_trend"] == TEMPLATE_SEED_PARAMETERS["ema_rsi_atr"]["ema_trend"]


def test_mutate_stays_in_bounds_and_crossover_mixes() -> None:
    gen = StrategyGenerator(seed=2)
    a = gen.generate("ema_rsi_atr", 1)[0]
    mutated = gen.mutate(a, rate=1.0, scale=0.5)
    template = get_template("ema_rsi_atr")
    for spec in template.params:
        assert spec.low <= mutated.parameters[spec.name] <= spec.high
    b = gen.generate("ema_rsi_atr", 1)[0]
    child = gen.crossover(a, b)
    for spec in template.params:
        assert child.parameters[spec.name] in (a.parameters[spec.name], b.parameters[spec.name])


# --------------------------------------------------------------------------
# Fitness + evaluator gate
# --------------------------------------------------------------------------
def test_compute_fitness_formula() -> None:
    # 0.4*2 + 0.3*0.8 + 0.2*min(1.5,5) - 0.1*0.1*10 = 0.8+0.24+0.3-0.1 = 1.24
    assert math.isclose(
        compute_fitness(sharpe=2.0, stability=0.8, profit_factor=1.5, max_drawdown=0.1),
        1.24,
        abs_tol=1e-6,
    )


def _result(**kw) -> EvaluationResult:
    base = dict(
        genome=StrategyGenome("ema_rsi_atr", {}),
        metrics={"track_days": 120, "dsr_pvalue": 0.01},
        monte_carlo={}, walk_forward=[],
        sharpe=1.5, profit_factor=1.8, max_drawdown=0.1,
        stability_score=0.7, consistency_score=0.7,
        in_sample_sharpe=1.5, out_sample_sharpe=1.4, overfit=False, total_trades=40,
    )
    base.update(kw)
    result = EvaluationResult(**base)
    result.fitness = compute_fitness(
        sharpe=result.sharpe, stability=result.stability_score,
        profit_factor=result.profit_factor, max_drawdown=result.max_drawdown,
    )
    return result


def test_promotion_gate_accepts_strong_strategy() -> None:
    verdict = StrategyEvaluator().evaluate_promotion(_result())
    assert verdict.passed
    assert verdict.decision.value == "PROMOTED"


def test_promotion_gate_rejects_overfit_and_weak() -> None:
    weak = _result(overfit=True, sharpe=0.2, max_drawdown=0.5, stability_score=0.1,
                   consistency_score=0.1, total_trades=3)
    verdict = StrategyEvaluator().evaluate_promotion(weak)
    assert not verdict.passed
    assert len(verdict.reasons) >= 4


# --------------------------------------------------------------------------
# Repository (DB)
# --------------------------------------------------------------------------
def test_repository_dedup_and_versioning(db_session) -> None:
    repo = ResearchRepository(db_session)
    genome = StrategyGenome("ema_rsi_atr", {"ema_trend": 200, "rsi_period": 14})

    strat1, created1 = repo.get_or_create_strategy(genome)
    strat2, created2 = repo.get_or_create_strategy(genome)
    assert created1 and not created2
    assert strat1.id == strat2.id  # dedup by signature

    repo.add_version(strat1, _result(sharpe=1.0))
    v2 = repo.add_version(strat1, _result(sharpe=2.0))
    assert v2.version == 2
    db_session.refresh(strat1)
    assert strat1.best_version_id == v2.id  # higher fitness wins


# --------------------------------------------------------------------------
# Feature store + hypotheses (DB)
# --------------------------------------------------------------------------
def test_feature_store_scores_features(db_session) -> None:
    seed_candles(db_session, n=400)
    results = FeatureStore(db_session).compute("BTC_USDT", "1h")
    assert len(results) >= 5
    names = {r["name"] for r in results}
    assert "atr_pct" in names
    for r in results:
        assert 0.0 <= r["importance_score"] <= 1.0


def test_hypothesis_builder_runs(db_session) -> None:
    seed_candles(db_session, n=400)
    records = HypothesisBuilder(db_session).test_all("BTC_USDT", "1h")
    assert len(records) == 8
    for rec in records:
        assert rec.status in ("SUPPORTED", "REJECTED", "INCONCLUSIVE")
        assert 0.0 <= float(rec.p_value) <= 1.0


# --------------------------------------------------------------------------
# Engine end-to-end (DB)
# --------------------------------------------------------------------------
def test_engine_evaluate_and_run_loop(db_session) -> None:
    seed_candles(db_session, n=700)
    engine = StrategyResearchEngine(db_session, seed=5)

    genome = engine.generate_strategy()
    outcome = engine.evaluate_strategy(genome, "BTC_USDT", "1h")
    assert outcome is not None
    strategy, version, result = outcome
    assert isinstance(result.fitness, float)
    assert db_session.query(StrategyVersion).count() >= 1

    summary = engine.run_experiments("BTC_USDT", "1h", population=3)
    assert summary["evaluated"] >= 1
    assert db_session.query(ResearchStrategy).count() >= 1


def test_engine_returns_insufficient_when_no_data(db_session) -> None:
    engine = StrategyResearchEngine(db_session, seed=5)
    summary = engine.run_experiments("ETH_USDT", "1h", population=2)
    assert summary["evaluated"] == 0
