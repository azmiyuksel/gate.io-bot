"""Discovers and auto-tests derived feature combinations.

Synthesizes new features (e.g. ATR/Volume, RSI*ADX, a volatility-regime score),
scores each by correlation with the next-bar return plus a stability check, and
persists the survivors to ``discovered_features`` and the knowledge base.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.models import DiscoveredFeatureSpec, KnowledgeType
from app.models.entities import DiscoveredFeature, HistoricalCandle
from app.strategy_research.feature_store import _safe_corr

_EPS = 1e-9


def _adx(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = frame["high"], frame["low"], frame["close"]
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(period).mean().replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=frame.index).rolling(period).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=frame.index).rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(period).mean()


def _derived_features(frame: pd.DataFrame) -> dict[str, tuple[str, pd.Series]]:
    close, high, low, vol = frame["close"], frame["high"], frame["low"], frame["volume"]
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    adx = _adx(frame)
    realized_vol = close.pct_change().rolling(20).std()
    vol_median = realized_vol.rolling(100).median()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    return {
        "atr_over_volume": ("ATR / Volume", atr / (vol + _EPS)),
        "rsi_times_adx": ("RSI * ADX / 100", rsi * adx / 100),
        "volatility_regime_score": ("realized_vol / median(realized_vol)", realized_vol / (vol_median + _EPS)),
        "ema_gap_over_atr": ("(EMA20 - EMA50) / ATR", (ema20 - ema50) / (atr + _EPS)),
        "volume_weighted_momentum": ("return * volume_z", close.pct_change() * ((vol - vol.rolling(50).mean()) / vol.rolling(50).std())),
    }


class FeatureDiscovery:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.kb = KnowledgeBase(db)

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
                {"open": float(r.open), "high": float(r.high), "low": float(r.low),
                 "close": float(r.close), "volume": float(r.volume)}
                for r in rows
            ]
        )

    @staticmethod
    def _stability(series: pd.Series, forward: pd.Series, chunks: int = 4) -> float:
        n = len(series)
        if n < chunks * 20:
            return 0.0
        size = n // chunks
        signs = []
        for i in range(chunks):
            c = _safe_corr(series.iloc[i * size:(i + 1) * size], forward.iloc[i * size:(i + 1) * size])
            if abs(c) > 0.01:
                signs.append(1 if c > 0 else -1)
        if not signs:
            return 0.0
        return round(max(signs.count(1), signs.count(-1)) / len(signs), 6)

    def discover(
        self, symbol: str = "BTC_USDT", timeframe: str = "1h", cycle_id: int | None = None
    ) -> list[DiscoveredFeatureSpec]:
        frame = self._load_frame(symbol, timeframe)
        if frame.empty or len(frame) < 120:
            return []

        forward = frame["close"].shift(-1) / frame["close"] - 1
        results: list[DiscoveredFeatureSpec] = []

        for name, (formula, series) in _derived_features(frame).items():
            series = series.replace([np.inf, -np.inf], np.nan)
            corr = _safe_corr(series, forward)
            stability = self._stability(series, forward)
            spec = DiscoveredFeatureSpec(
                name=name, formula=formula,
                correlation_with_profit=round(corr, 6),
                importance=round(abs(corr), 6),
                stability=stability,
            )
            results.append(spec)
            self._upsert(symbol, timeframe, spec, cycle_id)
            if abs(corr) >= 0.03 and stability >= 0.5:
                self.kb.record(
                    KnowledgeType.feature, f"Useful derived feature: {name}",
                    f"{formula} correlates {corr:+.4f} with next-bar return (stability {stability:.2f})",
                    symbol=symbol, confidence=min(1.0, abs(corr) * 10), support=len(frame),
                    cycle_id=cycle_id, payload={"correlation": corr, "stability": stability},
                )

        self.db.commit()
        results.sort(key=lambda r: r.importance, reverse=True)
        return results

    def _upsert(self, symbol: str, timeframe: str, spec: DiscoveredFeatureSpec, cycle_id: int | None) -> None:
        from decimal import Decimal

        record = (
            self.db.query(DiscoveredFeature)
            .filter(DiscoveredFeature.name == spec.name)
            .filter(DiscoveredFeature.symbol == symbol)
            .filter(DiscoveredFeature.timeframe == timeframe)
            .first()
        )
        if record is None:
            record = DiscoveredFeature(name=spec.name, symbol=symbol, timeframe=timeframe)
            self.db.add(record)
        record.formula = spec.formula
        record.correlation_with_profit = Decimal(str(spec.correlation_with_profit))
        record.importance_score = Decimal(str(spec.importance))
        record.stability_score = Decimal(str(spec.stability))
        record.cycle_id = cycle_id
