"""Strategy clustering for de-duplication and family grouping.

Groups strategies by normalized parameter vector + performance signature using
K-Means. Each strategy is assigned a ``family_id`` so the dashboard can show
strategy families and near-duplicates can be pruned (keep the best per family).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import ResearchStrategy, StrategyVersion
from app.strategy_research.models import get_template


def _normalized_vector(template_name: str, params: dict, sharpe: float, stability: float) -> list[float]:
    template = get_template(template_name)
    vec: list[float] = []
    for spec in template.params:
        value = float(params.get(spec.name, spec.low))
        span = (spec.high - spec.low) or 1.0
        vec.append((value - spec.low) / span)
    # Performance dimensions (bounded) so similar params with different behaviour split.
    vec.append(max(-1.0, min(3.0, sharpe)) / 3.0)
    vec.append(max(0.0, min(1.0, stability)))
    return vec


class StrategyClusterer:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _best_versions(self) -> list[tuple[ResearchStrategy, StrategyVersion]]:
        pairs = []
        for strat in self.db.query(ResearchStrategy).all():
            best = (
                self.db.query(StrategyVersion)
                .filter(StrategyVersion.strategy_id == strat.id)
                .order_by(StrategyVersion.fitness.desc())
                .first()
            )
            if best is not None:
                pairs.append((strat, best))
        return pairs

    def cluster(self, k: int | None = None, persist: bool = True) -> dict[int, int]:
        pairs = self._best_versions()
        if len(pairs) < 2:
            return {}

        matrix = [
            _normalized_vector(s.template, v.parameters, float(v.sharpe), float(v.stability_score))
            for s, v in pairs
        ]

        k = k or max(1, min(len(pairs) // 2, 6))
        labels = self._kmeans_labels(matrix, k)

        assignment: dict[int, int] = {}
        for (strat, _), label in zip(pairs, labels):
            assignment[strat.id] = int(label)
            if persist:
                strat.family_id = int(label)
        if persist:
            self.db.commit()
        return assignment

    @staticmethod
    def _kmeans_labels(matrix: list[list[float]], k: int) -> list[int]:
        try:
            import numpy as np
            from sklearn.cluster import KMeans

            X = np.array(matrix, dtype=float)
            k = max(1, min(k, len(matrix)))
            model = KMeans(n_clusters=k, random_state=42, n_init=10)
            return [int(x) for x in model.fit_predict(X)]
        except Exception:
            # Fallback: everything in one family.
            return [0] * len(matrix)

    def find_duplicates(self, threshold: float = 0.05) -> list[tuple[int, int]]:
        """Pairs of strategies whose normalized vectors are within ``threshold``."""
        pairs = self._best_versions()
        vectors = [
            (s.id, _normalized_vector(s.template, v.parameters, float(v.sharpe), float(v.stability_score)))
            for s, v in pairs
        ]
        dupes: list[tuple[int, int]] = []
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                dist = sum((a - b) ** 2 for a, b in zip(vectors[i][1], vectors[j][1])) ** 0.5
                if dist <= threshold:
                    dupes.append((vectors[i][0], vectors[j][0]))
        return dupes
