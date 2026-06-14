"""Generates and statistically tests market hypotheses.

Each hypothesis is a boolean condition over engineered features; we compare the
distribution of next-bar returns *under* the condition against the unconditional
distribution with a two-sample Welch t-test and Mann-Whitney U test. Bonferroni
correction is applied for multiple comparisons. A hypothesis is "supported" when
it shows a directional edge with adjusted p < 0.05 on a sufficient sample.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import HistoricalCandle, HypothesisTest
from app.strategy_research.models import HypothesisStatus


@dataclass
class Hypothesis:
    statement: str
    feature: str
    condition_desc: str
    predicate: Callable[[pd.DataFrame], pd.Series]


def _indicators(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame.copy()
    delta = f["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    f["rsi"] = 100 - (100 / (1 + rs))
    f["ema20"] = f["close"].ewm(span=20, adjust=False).mean()
    f["ema50"] = f["close"].ewm(span=50, adjust=False).mean()
    f["ema200"] = f["close"].ewm(span=200, adjust=False).mean()
    f["ret"] = f["close"].pct_change()
    f["vol20"] = f["ret"].rolling(20).std()
    f["vol_med"] = f["vol20"].rolling(100).median()
    f["volume_z"] = (f["volume"] - f["volume"].rolling(50).mean()) / f["volume"].rolling(50).std()
    f["volume_ma"] = f["volume"].rolling(20).mean()
    f["bb_mid"] = f["close"].rolling(20).mean()
    f["bb_std"] = f["close"].rolling(20).std()
    f["bb_lower"] = f["bb_mid"] - 2 * f["bb_std"]
    f["bb_upper"] = f["bb_mid"] + 2 * f["bb_std"]
    f["high_low_pct"] = (f["high"] - f["low"]) / f["close"]
    return f


def default_hypotheses() -> list[Hypothesis]:
    return [
        Hypothesis(
            statement="RSI < 30 in low volatility yields a mean-reversion edge",
            feature="rsi",
            condition_desc="rsi < 30 AND vol20 < vol_median",
            predicate=lambda f: (f["rsi"] < 30) & (f["vol20"] < f["vol_med"]),
        ),
        Hypothesis(
            statement="EMA20 above EMA50 (uptrend) precedes positive returns",
            feature="ema_cross",
            condition_desc="ema20 > ema50",
            predicate=lambda f: f["ema20"] > f["ema50"],
        ),
        Hypothesis(
            statement="Volume spike precedes a positive breakout move",
            feature="volume_z",
            condition_desc="volume_z > 2",
            predicate=lambda f: f["volume_z"] > 2,
        ),
        Hypothesis(
            statement="Overbought RSI > 70 precedes negative returns",
            feature="rsi",
            condition_desc="rsi > 70",
            predicate=lambda f: f["rsi"] > 70,
        ),
        Hypothesis(
            statement="Price near lower Bollinger Band precedes mean reversion upward",
            feature="bollinger_band",
            condition_desc="close <= bb_lower * 1.02",
            predicate=lambda f: f["close"] <= f["bb_lower"] * 1.02,
        ),
        Hypothesis(
            statement="High-low range expansion precedes momentum continuation",
            feature="range_expansion",
            condition_desc="high_low_pct > median(high_low_pct, 50) * 1.5",
            predicate=lambda f: (
                f["high_low_pct"] > f["high_low_pct"].rolling(50).median() * 1.5
            ),
        ),
        Hypothesis(
            statement="Volume climax (3x average) precedes trend exhaustion and reversal",
            feature="volume_climax",
            condition_desc="volume > volume_ma * 3",
            predicate=lambda f: f["volume"] > f["volume_ma"] * 3,
        ),
        Hypothesis(
            statement="Price above EMA200 in low volatility yields trend-following edge",
            feature="trend_regime",
            condition_desc="close > ema200 AND vol20 < vol_median",
            predicate=lambda f: (f["close"] > f["ema200"]) & (f["vol20"] < f["vol_med"]),
        ),
    ]


def _welch_t_test(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sided p-value for difference of means (Welch). Falls back to normal."""
    if len(a) < 5 or len(b) < 5:
        return 1.0
    ma, mb = a.mean(), b.mean()
    va, vb = a.var(ddof=1), b.var(ddof=1)
    denom = math.sqrt(va / len(a) + vb / len(b))
    if denom == 0:
        return 1.0
    t = (ma - mb) / denom
    try:
        from scipy import stats  # optional

        df = (va / len(a) + vb / len(b)) ** 2 / (
            (va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1)
        )
        return float(2 * stats.t.sf(abs(t), df))
    except Exception:
        return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def _mann_whitney_u(a: np.ndarray, b: np.ndarray) -> float:
    """Two-sided Mann-Whitney U p-value (non-parametric, handles fat tails)."""
    if len(a) < 5 or len(b) < 5:
        return 1.0
    try:
        from scipy import stats
        return float(stats.mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return _welch_t_test(a, b)


class HypothesisBuilder:
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
                    "open": float(r.open), "high": float(r.high), "low": float(r.low),
                    "close": float(r.close), "volume": float(r.volume),
                }
                for r in rows
            ]
        )

    def build(self) -> list[Hypothesis]:
        return default_hypotheses()

    def test(self, hypothesis: Hypothesis, symbol: str = "BTC_USDT", timeframe: str = "1h",
             persist: bool = True, bonferroni_n: int = 1) -> HypothesisTest:
        frame = self._load_frame(symbol, timeframe)
        forward = pd.Series(dtype="float64")
        edge = 0.0
        p_value = 1.0
        mw_p_value = 1.0
        sample = 0
        win_rate = 0.0

        if not frame.empty and len(frame) >= 120:
            f = _indicators(frame)
            forward = (f["close"].shift(-1) / f["close"] - 1)
            mask = hypothesis.predicate(f).fillna(False)
            cond = forward[mask].replace([np.inf, -np.inf], np.nan).dropna()
            base = forward.replace([np.inf, -np.inf], np.nan).dropna()
            sample = int(len(cond))
            if sample >= 30:
                edge = float(cond.mean() - base.mean())
                p_value = _welch_t_test(cond.to_numpy(), base.to_numpy())
                mw_p_value = _mann_whitney_u(cond.to_numpy(), base.to_numpy())
                win_rate = float((cond > 0).mean())

        # Bonferroni correction: p_bonf = min(p * n, 1.0)
        p_bonf = min(p_value * bonferroni_n, 1.0)
        mw_bonf = min(mw_p_value * bonferroni_n, 1.0)
        # Use the more conservative (larger) adjusted p-value.
        adjusted_p = max(p_bonf, mw_bonf)

        supported = sample >= 30 and abs(edge) > 0 and adjusted_p < 0.05
        expects_negative = "negative" in hypothesis.statement.lower()
        directional = (edge < 0) if expects_negative else (edge > 0)
        supported = supported and directional

        if sample < 30:
            status = HypothesisStatus.inconclusive
        elif supported:
            status = HypothesisStatus.supported
        else:
            status = HypothesisStatus.rejected

        record = HypothesisTest(
            statement=hypothesis.statement,
            feature=hypothesis.feature,
            condition=hypothesis.condition_desc,
            status=str(status),
            supported=bool(supported),
            edge=round(edge, 6),
            p_value=round(adjusted_p, 6),
            sample_size=sample,
            symbol=symbol,
            timeframe=timeframe,
            result={
                "win_rate": round(win_rate, 4),
                "direction": "negative" if expects_negative else "positive",
                "raw_p_value": round(p_value, 6),
                "mw_p_value": round(mw_p_value, 6),
                "bonferroni_n": bonferroni_n,
            },
        )
        if persist:
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        return record

    def test_all(self, symbol: str = "BTC_USDT", timeframe: str = "1h") -> list[HypothesisTest]:
        hypotheses = self.build()
        n = len(hypotheses)
        return [self.test(h, symbol, timeframe, bonferroni_n=n) for h in hypotheses]
