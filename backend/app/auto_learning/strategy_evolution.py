"""Evolves new candidate strategies.

Seeds the population from the knowledge base's best-known parameters and applies
the research lab's genetic operators (mutation, crossover, perturbation) to
explore nearby and recombined variants. Generation only - evaluation/validation
happens downstream so nothing is trusted yet.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.auto_learning.knowledge_base import KnowledgeBase
from app.strategy_research.generator import StrategyGenerator
from app.strategy_research.models import StrategyGenome


class StrategyEvolution:
    def __init__(self, db: Session, seed: int | None = None) -> None:
        self.db = db
        self.generator = StrategyGenerator(seed)
        self.kb = KnowledgeBase(db)

    def evolve(self, count: int = 8, template: str = "ema_rsi_atr") -> list[StrategyGenome]:
        population: list[StrategyGenome] = [self.generator.seed_genome(template_name=template)]
        known = self.kb.successful_parameters(limit=4)

        # Mutate / perturb around known-good parameter sets (exploitation).
        for params in known:
            genome = StrategyGenome(template=template, parameters=dict(params), origin="seed")
            population.append(self.generator.mutate(genome, rate=0.4, scale=0.15))

        # Recombine the two best known strategies (crossover).
        if len(known) >= 2:
            a = StrategyGenome(template, dict(known[0]))
            b = StrategyGenome(template, dict(known[1]))
            population.append(self.generator.crossover(a, b))

        # Fill the rest with fresh exploration.
        while len(population) < count:
            population.extend(self.generator.generate(template, 1))

        return population[:count]
