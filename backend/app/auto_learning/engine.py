"""Auto Learning & Continuous Evolution engine.

Runs the learning loop:

    mine patterns -> generate hypotheses -> discover features -> evolve ->
    validate (BT/CV/WF/MC/robustness/paper proxy) -> rank -> promotion REQUEST

Critically, the loop never deploys anything. A passing candidate only produces a
``PromotionRequest`` in ``AWAITING_APPROVAL``; a human must explicitly approve it.
The engine never enables live trading, never changes risk limits and never
touches the circuit breaker (enforced structurally and by SafetyGuard).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.auto_learning.feature_discovery import FeatureDiscovery
from app.auto_learning.hypothesis_generator import HypothesisGenerator
from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.meta_learning import MetaLearning
from app.auto_learning.models import (
    KnowledgeType,
    LearningCycleStatus,
    PromotionRequestStatus,
)
from app.auto_learning.pattern_miner import PatternMiner
from app.auto_learning.ranking_engine import RankingEngine
from app.auto_learning.safety import SafetyGuard
from app.auto_learning.strategy_evolution import StrategyEvolution
from app.auto_learning.validation_pipeline import ValidationPipeline
from app.core.config import get_settings
from app.models.entities import (
    KnowledgeEntry,
    LearningCycle,
    LearningReport,
    PromotionRequest,
    ResearchStrategy,
    StrategyVersion,
)
from app.strategy_research.models import StrategyStatus
from app.strategy_research.repository import ResearchRepository


class AutoLearningEngine:
    def __init__(self, db: Session, seed: int | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.kb = KnowledgeBase(db)
        self.miner = PatternMiner(db)
        self.hypotheses = HypothesisGenerator(db)
        self.features = FeatureDiscovery(db)
        self.evolution = StrategyEvolution(db, seed)
        self.meta = MetaLearning(db)
        self.pipeline = ValidationPipeline(db)
        self.ranking = RankingEngine(db)
        self.repo = ResearchRepository(db)
        self.safety = SafetyGuard(db)

    # ------------------------------------------------------------------
    # Learning loop
    # ------------------------------------------------------------------
    def run_cycle(
        self, symbol: str = "BTC_USDT", timeframe: str = "1h", population: int | None = None
    ) -> dict:
        population = population or self.settings.learning_population
        safety_before = self.safety.snapshot()

        cycle = LearningCycle(status=str(LearningCycleStatus.running), symbol=symbol, timeframe=timeframe)
        self.db.add(cycle)
        self.db.commit()
        self.db.refresh(cycle)

        try:
            patterns = self.miner.mine(symbol, cycle.id)
            hypotheses = self.hypotheses.generate_and_test(symbol, timeframe, cycle.id)
            features = self.features.discover(symbol, timeframe, cycle.id)
            self.meta.learn(symbol, cycle.id)

            genomes = self.evolution.evolve(population)
            validated = 0
            promotion_requests = 0

            for genome in genomes:
                outcome_pair = self.pipeline.validate(genome, symbol, timeframe)
                if outcome_pair is None:
                    continue
                outcome, result = outcome_pair
                validated += 1

                strategy, _ = self.repo.get_or_create_strategy(genome)
                version = self.repo.add_version(strategy, result)
                breakdown = self.ranking.rank(
                    sharpe=outcome.sharpe, stability=outcome.stability,
                    consistency=outcome.consistency, max_drawdown=outcome.max_drawdown,
                    ruin_probability=outcome.ruin_probability, overfit=outcome.overfit,
                )
                self.ranking.persist(strategy.id, version.id, breakdown, cycle.id)

                gate = self.pipeline.gate(outcome)
                if (
                    outcome.passed
                    and gate.passed
                    and breakdown.total >= self.settings.learning_min_ranking
                ):
                    self._create_promotion_request(strategy, version, outcome, breakdown, gate.reasons)
                    promotion_requests += 1
                else:
                    self._record_failure(strategy, outcome, gate.reasons, cycle.id)

            cycle.patterns_found = len(patterns)
            cycle.hypotheses_generated = len(hypotheses)
            cycle.features_discovered = len(features)
            cycle.strategies_evolved = len(genomes)
            cycle.strategies_validated = validated
            cycle.promotion_requests = promotion_requests
            cycle.summary = {
                "supported_hypotheses": sum(1 for h in hypotheses if h.supported),
                "top_feature": features[0].name if features else None,
            }
            cycle.status = str(LearningCycleStatus.completed)
            cycle.completed_at = datetime.now(UTC)
            self.db.commit()
        except Exception as exc:  # keep the cycle auditable on failure
            cycle.status = str(LearningCycleStatus.failed)
            cycle.error = str(exc)
            cycle.completed_at = datetime.now(UTC)
            self.db.commit()
            raise

        # Safety invariant: nothing safety-relevant may have changed.
        safety_after = self.safety.snapshot()
        safety_ok = self.safety.verify_unchanged(safety_before, safety_after)

        return {
            "cycle_id": cycle.id,
            "status": cycle.status,
            "patterns_found": cycle.patterns_found,
            "hypotheses_generated": cycle.hypotheses_generated,
            "features_discovered": cycle.features_discovered,
            "strategies_evolved": cycle.strategies_evolved,
            "strategies_validated": cycle.strategies_validated,
            "promotion_requests": cycle.promotion_requests,
            "safety_invariants_held": safety_ok,
        }

    # ------------------------------------------------------------------
    # Promotion workflow (human-in-the-loop)
    # ------------------------------------------------------------------
    def _create_promotion_request(
        self, strategy: ResearchStrategy, version: StrategyVersion, outcome, breakdown, reasons: list[str]
    ) -> PromotionRequest:
        existing = (
            self.db.query(PromotionRequest)
            .filter(PromotionRequest.strategy_id == strategy.id)
            .filter(PromotionRequest.status == str(PromotionRequestStatus.awaiting_approval))
            .first()
        )
        if existing is not None:
            return existing
        request = PromotionRequest(
            strategy_id=strategy.id,
            version_id=version.id,
            status=str(PromotionRequestStatus.awaiting_approval),
            ranking_score=Decimal(str(round(breakdown.total, 2))),
            gate_passed=True,
            gate_reasons=reasons,
            validation={
                "sharpe": outcome.sharpe,
                "profit_factor": outcome.profit_factor,
                "consistency": outcome.consistency,
                "max_drawdown": outcome.max_drawdown,
                "ruin_probability": outcome.ruin_probability,
                "stages": [
                    {"stage": s.stage.value, "passed": s.passed, "detail": s.detail}
                    for s in outcome.stages
                ],
            },
            requested_by="auto_learning",
        )
        self.db.add(request)
        self.db.commit()
        self.db.refresh(request)
        return request

    def approve_promotion(
        self, request_id: int, decided_by: str, note: str | None = None
    ) -> PromotionRequest | None:
        request = self.db.get(PromotionRequest, request_id)
        if request is None or request.status != str(PromotionRequestStatus.awaiting_approval):
            return None
        request.status = str(PromotionRequestStatus.approved)
        request.decided_by = decided_by
        request.decision_note = note
        request.decided_at = datetime.now(UTC)

        # Human-approved: mark the research strategy PROMOTED. This does NOT enable
        # live trading, change risk limits or touch the circuit breaker.
        strategy = self.db.get(ResearchStrategy, request.strategy_id)
        if strategy is not None:
            strategy.status = str(StrategyStatus.promoted)
            strategy.updated_at = datetime.now(UTC)
        self.kb.record(
            KnowledgeType.meta, "Strategy approved for production",
            f"Strategy #{request.strategy_id} approved by {decided_by}",
            confidence=1.0, payload={"request_id": request_id},
        )
        self.db.commit()
        self.db.refresh(request)
        return request

    def reject_promotion(
        self, request_id: int, decided_by: str, note: str | None = None
    ) -> PromotionRequest | None:
        request = self.db.get(PromotionRequest, request_id)
        if request is None or request.status != str(PromotionRequestStatus.awaiting_approval):
            return None
        request.status = str(PromotionRequestStatus.rejected)
        request.decided_by = decided_by
        request.decision_note = note
        request.decided_at = datetime.now(UTC)
        strategy = self.db.get(ResearchStrategy, request.strategy_id)
        if strategy is not None:
            strategy.status = str(StrategyStatus.rejected)
        self.db.commit()
        self.db.refresh(request)
        return request

    # ------------------------------------------------------------------
    # Failure learning
    # ------------------------------------------------------------------
    def _record_failure(
        self, strategy: ResearchStrategy, outcome, reasons: list[str], cycle_id: int | None
    ) -> KnowledgeEntry:
        return self.kb.record(
            KnowledgeType.failure,
            f"Rejected candidate {strategy.name}",
            "Failed promotion: " + "; ".join(reasons),
            confidence=0.6, support=0, cycle_id=cycle_id,
            payload={
                "sharpe": outcome.sharpe,
                "consistency": outcome.consistency,
                "overfit": outcome.overfit,
                "ranking": outcome.ranking_total,
            },
        )

    # ------------------------------------------------------------------
    # Control / status / reporting
    # ------------------------------------------------------------------
    def stop(self) -> dict:
        running = (
            self.db.query(LearningCycle)
            .filter(LearningCycle.status == str(LearningCycleStatus.running))
            .all()
        )
        for cycle in running:
            cycle.status = str(LearningCycleStatus.stopped)
            cycle.completed_at = datetime.now(UTC)
        self.db.commit()
        return {"stopped_cycles": len(running)}

    def status(self) -> dict:
        latest = (
            self.db.query(LearningCycle)
            .order_by(LearningCycle.started_at.desc())
            .first()
        )
        pending = (
            self.db.query(PromotionRequest)
            .filter(PromotionRequest.status == str(PromotionRequestStatus.awaiting_approval))
            .count()
        )
        return {
            "enabled": self.settings.learning_enabled,
            "latest_cycle": {
                "id": latest.id,
                "status": latest.status,
                "started_at": latest.started_at.isoformat(),
                "strategies_validated": latest.strategies_validated,
                "promotion_requests": latest.promotion_requests,
            }
            if latest
            else None,
            "pending_approvals": pending,
            "knowledge": self.kb.stats(),
            "safety_invariants": list(self.safety.invariants()),
        }

    def weekly_report(self, days: int = 7) -> LearningReport:
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        patterns = (
            self.db.query(KnowledgeEntry)
            .filter(KnowledgeEntry.knowledge_type == str(KnowledgeType.pattern))
            .filter(KnowledgeEntry.created_at >= start)
            .count()
        )
        failures = (
            self.db.query(KnowledgeEntry)
            .filter(KnowledgeEntry.knowledge_type == str(KnowledgeType.failure))
            .filter(KnowledgeEntry.created_at >= start)
            .count()
        )
        candidates = (
            self.db.query(ResearchStrategy)
            .filter(ResearchStrategy.created_at >= start)
            .count()
        )
        requests = (
            self.db.query(PromotionRequest)
            .filter(PromotionRequest.created_at >= start)
            .count()
        )
        report = LearningReport(
            period_start=start,
            period_end=end,
            patterns_learned=patterns,
            failed_strategies=failures,
            new_candidates=candidates,
            promotion_requests=requests,
            report_data={"generated_at": end.isoformat()},
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report
