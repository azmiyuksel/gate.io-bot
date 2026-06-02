from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.auto_learning.engine import AutoLearningEngine
from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.models import (
    KnowledgeType,
    PromotionGateThresholds,
    SAFETY_INVARIANTS,
    compute_ranking,
)
from app.auto_learning.safety import SafetyGuard, SafetyViolation
from app.auto_learning.strategy_evolution import StrategyEvolution
from app.auto_learning.validation_pipeline import ValidationPipeline
from app.models.entities import (
    CircuitBreakerEvent,
    HistoricalCandle,
    PromotionRequest,
    StrategySettings,
)
from app.strategy_research.models import StrategyGenome, get_template
from app.strategy_research.repository import ResearchRepository

BASE_TS = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())


def seed_candles(db, symbol="BTC_USDT", timeframe="1h", n=700, seed=11) -> None:
    import random

    rng = random.Random(seed)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    price = 100.0
    for i in range(n):
        price *= 1 + 0.0005 + rng.uniform(-0.01, 0.01)
        db.add(
            HistoricalCandle(
                symbol=symbol, timeframe=timeframe,
                timestamp=start + timedelta(hours=i),
                open=Decimal(str(round(price * (1 + rng.uniform(-0.003, 0.003)), 4))),
                high=Decimal(str(round(price * 1.006, 4))),
                low=Decimal(str(round(price * 0.994, 4))),
                close=Decimal(str(round(price, 4))),
                volume=Decimal(str(round(rng.uniform(50, 150), 4))),
                source="test",
            )
        )
    db.commit()


# --------------------------------------------------------------------------
# Ranking + gate (promotion gate tests)
# --------------------------------------------------------------------------
def test_ranking_weights_sum_to_100_for_perfect() -> None:
    r = compute_ranking(
        sharpe=3.0, stability=1.0, consistency=1.0,
        max_drawdown=0.0, ruin_probability=0.0, overfit=False,
    )
    assert abs(r.total - 100.0) < 1e-6


def test_ranking_overfit_zeroes_robustness() -> None:
    r = compute_ranking(
        sharpe=3.0, stability=1.0, consistency=1.0,
        max_drawdown=0.0, ruin_probability=0.0, overfit=True,
    )
    # Robustness (30 pts) zeroed by overfit.
    assert r.robustness == 0.0
    assert r.total <= 70.0


def test_promotion_gate_thresholds_match_spec() -> None:
    t = PromotionGateThresholds()
    assert t.min_sharpe == 1.5
    assert t.min_profit_factor == 1.3
    assert t.min_consistency == 0.60


def test_validation_gate_rejects_weak(db_session) -> None:
    from app.auto_learning.models import ValidationOutcome

    pipeline = ValidationPipeline(db_session)
    weak = ValidationOutcome(
        passed=False, stages=[], sharpe=0.3, profit_factor=1.0, consistency=0.2,
        stability=0.1, max_drawdown=0.4, ruin_probability=0.5, overfit=True,
        ranking_total=10.0, parameters={},
    )
    gate = pipeline.gate(weak)
    assert not gate.passed
    assert len(gate.reasons) >= 4


# --------------------------------------------------------------------------
# Strategy evolution / mutation
# --------------------------------------------------------------------------
def test_evolution_produces_valid_population(db_session) -> None:
    population = StrategyEvolution(db_session, seed=3).evolve(count=6)
    assert len(population) == 6
    template = get_template("ema_rsi_atr")
    for genome in population:
        for spec in template.params:
            assert spec.low <= genome.parameters[spec.name] <= spec.high


# --------------------------------------------------------------------------
# Knowledge base consistency
# --------------------------------------------------------------------------
def test_knowledge_base_roundtrip(db_session) -> None:
    kb = KnowledgeBase(db_session)
    kb.record(KnowledgeType.pattern, "t1", "desc", confidence=0.9, support=10)
    kb.record(KnowledgeType.failure, "t2", "desc2", confidence=0.5)
    patterns = kb.query(KnowledgeType.pattern)
    assert len(patterns) == 1
    assert patterns[0].title == "t1"
    assert kb.stats()["knowledge_entries"] == 2


# --------------------------------------------------------------------------
# Safety restriction tests
# --------------------------------------------------------------------------
def test_safety_guard_hard_locks(db_session) -> None:
    guard = SafetyGuard(db_session)
    for method in (
        guard.assert_can_promote_automatically,
        guard.assert_can_modify_risk_limits,
        guard.assert_can_touch_circuit_breaker,
    ):
        try:
            method()
            raise AssertionError("expected SafetyViolation")
        except SafetyViolation:
            pass
    assert len(SAFETY_INVARIANTS) == 4


def test_learning_cycle_does_not_touch_live_or_breaker(db_session) -> None:
    # Establish baseline live + breaker state.
    settings = StrategySettings(is_enabled=True)
    db_session.add(settings)
    db_session.add(CircuitBreakerEvent(state="ARMED", scope="MANUAL", reason="seed"))
    seed_candles(db_session, n=700)
    db_session.commit()

    before = SafetyGuard(db_session).snapshot()
    summary = AutoLearningEngine(db_session, seed=5).run_cycle("BTC_USDT", "1h", population=3)
    after = SafetyGuard(db_session).snapshot()

    # The learning cycle must not change live-trading state or the breaker.
    assert summary["safety_invariants_held"] is True
    assert before["live_strategy_enabled"] == after["live_strategy_enabled"] is True
    assert before["circuit_breaker_event_count"] == after["circuit_breaker_event_count"]
    assert before["live_daily_max_loss_pct"] == after["live_daily_max_loss_pct"]


# --------------------------------------------------------------------------
# Promotion requires human approval (no auto-deploy)
# --------------------------------------------------------------------------
def test_promotion_requires_human_approval(db_session) -> None:
    engine = AutoLearningEngine(db_session, seed=5)
    # Manually create an awaiting-approval request to exercise the human gate.
    repo = ResearchRepository(db_session)
    strategy, _ = repo.get_or_create_strategy(StrategyGenome("ema_rsi_atr", {"ema_trend": 200}))
    req = PromotionRequest(
        strategy_id=strategy.id, status="AWAITING_APPROVAL", gate_passed=True,
        ranking_score=Decimal("80"),
    )
    db_session.add(req)
    db_session.commit()

    # Before approval: strategy is not promoted.
    assert strategy.status != "PROMOTED"

    approved = engine.approve_promotion(req.id, decided_by="admin@example.com", note="ok")
    assert approved is not None
    assert approved.status == "APPROVED"
    db_session.refresh(strategy)
    assert strategy.status == "PROMOTED"
    # Live trading still not enabled by promotion (no StrategySettings touched).
    assert db_session.query(StrategySettings).count() == 0


def test_weekly_report_generates(db_session) -> None:
    kb = KnowledgeBase(db_session)
    kb.record(KnowledgeType.pattern, "p", "d")
    report = AutoLearningEngine(db_session).weekly_report(7)
    assert report.patterns_learned >= 1
