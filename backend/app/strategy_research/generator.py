"""Strategy generation: indicator combinations, rule mutation, crossover.

Operates generically over a template's search space (``models.StrategyTemplate``),
so the same generator works for any registered template. Genetic operators
(mutation/crossover) underpin the research loop's evolutionary search.
"""
from __future__ import annotations

import random

import numpy as np

from app.strategy_research.models import (
    StrategyGenome,
    StrategyTemplate,
    get_template,
)
from app.strategy_research.feature_store import FEATURE_PARAM_MAPPING

# Canonical seed parameters per template.
TEMPLATE_SEED_PARAMETERS: dict[str, dict[str, float | int]] = {
    "ema_rsi_atr": {
        "ema_trend": 200,
        "ema_entry": 20,
        "rsi_period": 14,
        "rsi_threshold": 35.0,
        "atr_period": 14,
        "atr_multiplier": 1.5,
        "reward_risk": 2.0,
        "max_capital_per_trade_pct": 0.01,
        "trailing_stop_pct": 0.01,
    },
    "macd": {
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
        "atr_period": 14,
        "atr_multiplier": 2.0,
        "reward_risk": 2.0,
        "max_capital_per_trade_pct": 0.01,
        "trailing_stop_pct": 0.01,
    },
    "bollinger_bands": {
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "rsi_oversold": 35.0,
        "atr_period": 14,
        "atr_multiplier": 1.5,
        "reward_risk": 2.5,
        "max_capital_per_trade_pct": 0.01,
        "trailing_stop_pct": 0.01,
    },
}


def get_seed_parameters(template_name: str) -> dict[str, float | int]:
    return TEMPLATE_SEED_PARAMETERS.get(template_name, {})


class StrategyGenerator:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    # --- A) Indicator combination / random sampling ---
    def generate(self, template_name: str = "ema_rsi_atr", count: int = 1) -> list[StrategyGenome]:
        template = get_template(template_name)
        return [
            StrategyGenome(
                template=template_name,
                parameters=template.default_genome(self.rng),
                origin="generated",
            )
            for _ in range(count)
        ]

    def seed_genome(self, template_name: str = "ema_rsi_atr") -> StrategyGenome:
        template = get_template(template_name)
        seeds = get_seed_parameters(template_name)
        params = {p.name: seeds.get(p.name, p.sample(self.rng)) for p in template.params}
        return StrategyGenome(template=template_name, parameters=params, origin="seed")

    # --- B) Rule mutation engine ---
    def mutate(self, genome: StrategyGenome, rate: float = 0.3, scale: float = 0.2) -> StrategyGenome:
        template = get_template(genome.template)
        params = dict(genome.parameters)
        for spec in template.params:
            if self.rng.random() > rate:
                continue
            current = float(params.get(spec.name, spec.sample(self.rng)))
            span = (spec.high - spec.low) * scale
            mutated = current + self.rng.uniform(-span, span)
            params[spec.name] = spec.clamp(mutated)
        return StrategyGenome(
            template=genome.template,
            parameters=params,
            origin="mutated",
            parent_ids=list(genome.parent_ids),
        )

    # --- Crossover (genetic recombination) ---
    def crossover(self, a: StrategyGenome, b: StrategyGenome) -> StrategyGenome:
        if a.template != b.template:
            raise ValueError("Cannot cross strategies from different templates")
        template = get_template(a.template)
        params = {}
        for spec in template.params:
            source = a if self.rng.random() < 0.5 else b
            params[spec.name] = spec.clamp(float(source.parameters[spec.name]))
        return StrategyGenome(template=a.template, parameters=params, origin="crossover")

    # --- C) Feature-driven generation ---
    def generate_feature_driven(
        self, feature_importances: dict[str, float], template_name: str = "ema_rsi_atr"
    ) -> StrategyGenome:
        """Bias sampling toward parameters tied to high-importance features.

        Uses FEATURE_PARAM_MAPPING to find which features affect each parameter,
        then averages their importance scores. Important params get sampled near
        the seed (exploitation); unimportant ones are sampled widely (exploration).
        """
        template: StrategyTemplate = get_template(template_name)
        seeds = get_seed_parameters(template_name)

        # Compute per-parameter aggregated importance from feature mapping.
        param_importance: dict[str, float] = {}
        for spec in template.params:
            importance_values = []
            for feature_name, affected_params in FEATURE_PARAM_MAPPING.items():
                if spec.name in affected_params:
                    importance_values.append(feature_importances.get(feature_name, 0.0))
            param_importance[spec.name] = (
                float(np.mean(importance_values)) if importance_values else 0.0
            )

        params = {}
        for spec in template.params:
            pi = param_importance.get(spec.name, 0.0)
            if pi >= 0.5:
                base = float(seeds.get(spec.name, spec.sample(self.rng)))
                span = (spec.high - spec.low) * 0.1
                params[spec.name] = spec.clamp(base + self.rng.uniform(-span, span))
            else:
                params[spec.name] = spec.sample(self.rng)
        return StrategyGenome(template=template_name, parameters=params, origin="generated")
