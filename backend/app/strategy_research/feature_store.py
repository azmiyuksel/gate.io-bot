"""Central feature store.

Computes a catalogue of price/volume/volatility/trend/order-flow features from
the historical candle store and scores each by:

* correlation_with_profit - Pearson corr of the feature vs the next-bar return
* importance_score        - |correlation| (normalized 0..1)
* stability_score         - how consistently the correlation sign holds across
                            sub-periods (robustness)

Results are persisted to ``feature_store`` and consumed by the generator
(feature-driven generation) and the dashboard heatmap.
"""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import FeatureRecord, HistoricalCandle
from app.strategy_research.models import FeatureCategory

_EPS = 1e-9


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    mask = a.notna() & b.notna()
    if mask.sum() < 10:
        return 0.0
    av, bv = a[mask], b[mask]
    if av.std() < _EPS or bv.std() < _EPS:
        return 0.0
    return float(np.clip(av.corr(bv), -1.0, 1.0))


def _build_features(frame: pd.DataFrame) -> dict[str, tuple[FeatureCategory, pd.Series]]:
    close, high, low, opn, vol = (
        frame["close"], frame["high"], frame["low"], frame["open"], frame["volume"]
    )
    ret = close.pct_change()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    rng = (high - low).replace(0, np.nan)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    return {
        "return_1": (FeatureCategory.price, ret),
        "price_vs_ema50": (FeatureCategory.price, (close - ema50) / ema50),
        "volume_zscore": (FeatureCategory.volume, (vol - vol.rolling(50).mean()) / vol.rolling(50).std()),
        "volume_change": (FeatureCategory.volume, vol.pct_change().clip(-5, 5)),
        "atr_pct": (FeatureCategory.volatility, atr / close),
        "realized_vol": (FeatureCategory.volatility, ret.rolling(20).std()),
        "ema_trend_gap": (FeatureCategory.trend, (ema20 - ema50) / ema50),
        "ema20_slope": (FeatureCategory.trend, ema20.diff() / ema20),
        "close_in_range": (FeatureCategory.order_flow, (close - low) / rng),
        "signed_volume": (FeatureCategory.order_flow, ((close - opn) / rng) * np.sign(vol)),
    }


class FeatureStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _load_frame(self, symbol: str, timeframe: str, limit: int = 5000) -> pd.DataFrame:
        rows = self.db.scalars(
            select(HistoricalCandle)
            .where(HistoricalCandle.symbol == symbol)
            .where(HistoricalCandle.timeframe == timeframe)
            .order_by(HistoricalCandle.timestamp.asc())
            .limit(limit)
        ).all()
        return pd.DataFrame(
            [
                {
                    "timestamp": r.timestamp,
                    "open": float(r.open),
                    "high": float(r.high),
                    "low": float(r.low),
                    "close": float(r.close),
                    "volume": float(r.volume),
                }
                for r in rows
            ]
        )

    def compute(self, symbol: str = "BTC_USDT", timeframe: str = "1h", persist: bool = True) -> list[dict]:
        frame = self._load_frame(symbol, timeframe)
        if frame.empty or len(frame) < 60:
            return []

        forward_return = frame["close"].shift(-1) / frame["close"] - 1
        features = _build_features(frame)
        results: list[dict] = []

        for name, (category, series) in features.items():
            series = series.replace([np.inf, -np.inf], np.nan)
            corr = _safe_corr(series, forward_return)
            stability = self._stability(series, forward_return)
            importance = abs(corr)
            results.append(
                {
                    "name": name,
                    "category": str(category),
                    "correlation_with_profit": round(corr, 6),
                    "importance_score": round(importance, 6),
                    "stability_score": round(stability, 6),
                }
            )
            if persist:
                self._upsert(symbol, timeframe, name, category, corr, importance, stability)

        if persist:
            self.db.commit()
        results.sort(key=lambda r: r["importance_score"], reverse=True)
        return results

    @staticmethod
    def _stability(series: pd.Series, forward_return: pd.Series, chunks: int = 4) -> float:
        """Fraction-based consistency of correlation sign across sub-periods."""
        n = len(series)
        if n < chunks * 20:
            return 0.0
        size = n // chunks
        signs = []
        for i in range(chunks):
            s = series.iloc[i * size : (i + 1) * size]
            f = forward_return.iloc[i * size : (i + 1) * size]
            c = _safe_corr(s, f)
            if abs(c) > 0.01:
                signs.append(1 if c > 0 else -1)
        if not signs:
            return 0.0
        dominant = max(signs.count(1), signs.count(-1))
        return round(dominant / len(signs), 6)

    def _upsert(
        self,
        symbol: str,
        timeframe: str,
        name: str,
        category: FeatureCategory,
        corr: float,
        importance: float,
        stability: float,
    ) -> None:
        record = (
            self.db.query(FeatureRecord)
            .filter(FeatureRecord.name == name)
            .filter(FeatureRecord.symbol == symbol)
            .filter(FeatureRecord.timeframe == timeframe)
            .first()
        )
        if record is None:
            record = FeatureRecord(name=name, symbol=symbol, timeframe=timeframe)
            self.db.add(record)
        record.category = str(category)
        record.correlation_with_profit = round(corr, 6)
        record.importance_score = round(importance, 6)
        record.stability_score = round(stability, 6)
        record.updated_at = datetime.now(UTC)

    def importances(self, symbol: str = "BTC_USDT", timeframe: str = "1h") -> dict[str, float]:
        rows = (
            self.db.query(FeatureRecord)
            .filter(FeatureRecord.symbol == symbol)
            .filter(FeatureRecord.timeframe == timeframe)
            .all()
        )
        return {r.name: float(r.importance_score) for r in rows}
