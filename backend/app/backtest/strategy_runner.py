from abc import ABC

import numpy as np
import pandas as pd


def _ema_sma_seed(series: pd.Series, period: int) -> pd.Series:
    """EMA with SMA seed — matches the live ``indicators.ema()`` formula.

    Pandas ``ewm(span=N, adjust=False)`` seeds from the first raw value, but
    the live engine seeds with the SMA of the first ``period`` values.  This
    function produces the same result so backtest EMA values match live exactly.
    """
    result = pd.Series(np.nan, index=series.index, dtype="float64")
    if len(series) < period:
        return result
    sma_seed = series.iloc[:period].mean()
    result.iloc[period - 1] = sma_seed
    alpha = 2.0 / (period + 1)
    prev = sma_seed
    for i in range(period, len(series)):
        val = (series.iloc[i] - prev) * alpha + prev
        result.iloc[i] = val
        prev = val
    return result


class BaseStrategy(ABC):
    def on_candle(self, candle: pd.Series) -> None:
        pass

    def should_buy(self) -> bool:
        return False

    def should_sell(self) -> bool:
        return False

    def position_size(self, equity: float, price: float) -> float:
        return 0


class MacdStrategy(BaseStrategy):
    def __init__(self, parameters: dict | None = None) -> None:
        params = parameters or {}
        self.macd_fast = int(params.get("macd_fast", 12))
        self.macd_slow = int(params.get("macd_slow", 26))
        self.macd_signal = int(params.get("macd_signal", 9))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = float(params.get("atr_multiplier", 2.0))
        self.reward_risk = float(params.get("reward_risk", 2.0))
        self.max_capital_per_trade_pct = float(params.get("max_capital_per_trade_pct", 0.01))
        self.max_risk_per_trade_pct = float(params.get("max_risk_per_trade_pct", 0.02))
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        ema_fast = _ema_sma_seed(frame["close"], self.macd_fast)
        ema_slow = _ema_sma_seed(frame["close"], self.macd_slow)
        frame["macd"] = ema_fast - ema_slow
        frame["macd_signal_line"] = _ema_sma_seed(frame["macd"], self.macd_signal)
        frame["macd_histogram"] = frame["macd"] - frame["macd_signal_line"]
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift()).abs(),
                (frame["low"] - frame["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr"] = tr.rolling(self.atr_period).mean()
        return frame.dropna()

    def on_candle(self, candle: pd.Series) -> None:
        self.current = candle

    def should_buy(self) -> bool:
        if self.current is None:
            return False
        return float(self.current.get("macd_histogram", 0)) > 0

    def should_sell(self) -> bool:
        return False

    def position_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        # Fixed-fractional RISK sizing: size so the loss if stopped out equals
        # max_risk_per_trade_pct of equity, scaled by the ATR stop distance, so
        # per-trade dollar risk is steady across calm/volatile regimes. Capped at
        # the notional limit (max_capital_per_trade_pct) to bound gross exposure.
        notional_cap = (equity * self.max_capital_per_trade_pct) / price
        if self.current is not None:
            atr = float(self.current.get("atr", 0.0) or 0.0)
            stop_distance = atr * self.atr_multiplier
            if stop_distance > 0:
                risk_budget = equity * self.max_risk_per_trade_pct
                return min(risk_budget / stop_distance, notional_cap)
        return notional_cap

    def risk_levels(self, entry: float) -> tuple[float, float]:
        if self.current is None:
            raise ValueError("Strategy has no active candle")
        risk = float(self.current["atr"]) * self.atr_multiplier
        stop_loss = entry - risk
        take_profit = entry + (risk * self.reward_risk)
        return stop_loss, take_profit


class BollingerBandsStrategy(BaseStrategy):
    def __init__(self, parameters: dict | None = None) -> None:
        params = parameters or {}
        self.bb_period = int(params.get("bb_period", 20))
        self.bb_std = float(params.get("bb_std", 2.0))
        self.rsi_period = int(params.get("rsi_period", 14))
        self.rsi_oversold = float(params.get("rsi_oversold", 35))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = float(params.get("atr_multiplier", 1.5))
        self.reward_risk = float(params.get("reward_risk", 2.5))
        self.max_capital_per_trade_pct = float(params.get("max_capital_per_trade_pct", 0.01))
        self.max_risk_per_trade_pct = float(params.get("max_risk_per_trade_pct", 0.02))
        # Tolerance band around the lower BB for the entry touch (fraction).
        # Was a hardcoded 0.005; now configurable so the optimizer can tune it.
        self.bb_lower_tolerance = float(params.get("bb_lower_tolerance", 0.005))
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["bb_mid"] = frame["close"].rolling(self.bb_period).mean()
        bb_std = frame["close"].rolling(self.bb_period).std()
        frame["bb_upper"] = frame["bb_mid"] + self.bb_std * bb_std
        frame["bb_lower"] = frame["bb_mid"] - self.bb_std * bb_std
        frame["bb_width"] = (frame["bb_upper"] - frame["bb_lower"]) / frame["bb_mid"]
        delta = frame["close"].diff()
        # Wilder smoothing (EWM alpha=1/period) — matches the live indicators.rsi().
        # The old SMA .rolling().mean() diverged from live RSI, causing
        # backtested entry signals to disagree with live entry signals.
        gain = delta.clip(lower=0).ewm(alpha=1 / self.rsi_period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / self.rsi_period, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        frame["rsi"] = 100 - (100 / (1 + rs))
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift()).abs(),
                (frame["low"] - frame["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr"] = tr.rolling(self.atr_period).mean()
        return frame.dropna()

    def on_candle(self, candle: pd.Series) -> None:
        self.current = candle

    def should_buy(self) -> bool:
        if self.current is None:
            return False
        price = float(self.current["close"])
        lower = float(self.current.get("bb_lower", 0))
        rsi = float(self.current.get("rsi", 50))
        return price <= lower * (1 + self.bb_lower_tolerance) and rsi < self.rsi_oversold

    def should_sell(self) -> bool:
        return False

    def position_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        # Fixed-fractional RISK sizing: size so the loss if stopped out equals
        # max_risk_per_trade_pct of equity, scaled by the ATR stop distance, so
        # per-trade dollar risk is steady across calm/volatile regimes. Capped at
        # the notional limit (max_capital_per_trade_pct) to bound gross exposure.
        notional_cap = (equity * self.max_capital_per_trade_pct) / price
        if self.current is not None:
            atr = float(self.current.get("atr", 0.0) or 0.0)
            stop_distance = atr * self.atr_multiplier
            if stop_distance > 0:
                risk_budget = equity * self.max_risk_per_trade_pct
                return min(risk_budget / stop_distance, notional_cap)
        return notional_cap

    def risk_levels(self, entry: float) -> tuple[float, float]:
        if self.current is None:
            raise ValueError("Strategy has no active candle")
        risk = float(self.current["atr"]) * self.atr_multiplier
        stop_loss = entry - risk
        take_profit = entry + (risk * self.reward_risk)
        return stop_loss, take_profit


class EmaRsiAtrStrategy(BaseStrategy):
    def __init__(self, parameters: dict | None = None) -> None:
        params = parameters or {}
        self.ema_trend = int(params.get("ema_trend", 200))
        self.ema_entry = int(params.get("ema_entry", 20))
        self.rsi_period = int(params.get("rsi_period", 14))
        self.rsi_threshold = float(params.get("rsi_threshold", 35))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = float(params.get("atr_multiplier", 1.5))
        self.reward_risk = float(params.get("reward_risk", 2))
        self.max_capital_per_trade_pct = float(params.get("max_capital_per_trade_pct", 0.01))
        self.max_risk_per_trade_pct = float(params.get("max_risk_per_trade_pct", 0.02))
        # EMA20 distance gate (fraction). Live capital_preservation uses 0.015;
        # made configurable so the optimizer can tune it rather than a hidden
        # hardcoded 0.01 that diverged from live.
        self.ema_entry_distance_pct = float(params.get("ema_entry_distance_pct", 0.015))
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["ema_trend"] = _ema_sma_seed(frame["close"], self.ema_trend)
        frame["ema_entry"] = _ema_sma_seed(frame["close"], self.ema_entry)
        delta = frame["close"].diff()
        # Wilder smoothing (EWM alpha=1/period) — matches the live indicators.rsi().
        gain = delta.clip(lower=0).ewm(alpha=1 / self.rsi_period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / self.rsi_period, adjust=False).mean()
        rs = gain / loss.replace(0, pd.NA)
        frame["rsi"] = 100 - (100 / (1 + rs))
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift()).abs(),
                (frame["low"] - frame["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr"] = tr.rolling(self.atr_period).mean()
        return frame.dropna()

    def on_candle(self, candle: pd.Series) -> None:
        self.current = candle

    def should_buy(self) -> bool:
        if self.current is None:
            return False
        price = float(self.current["close"])
        if price <= float(self.current["ema_trend"]):
            return False
        if float(self.current["rsi"]) >= self.rsi_threshold:
            return False
        distance = abs(price - float(self.current["ema_entry"])) / float(self.current["ema_entry"])
        return distance <= self.ema_entry_distance_pct

    def should_sell(self) -> bool:
        return False

    def position_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        # Fixed-fractional RISK sizing: size so the loss if stopped out equals
        # max_risk_per_trade_pct of equity, scaled by the ATR stop distance, so
        # per-trade dollar risk is steady across calm/volatile regimes. Capped at
        # the notional limit (max_capital_per_trade_pct) to bound gross exposure.
        notional_cap = (equity * self.max_capital_per_trade_pct) / price
        if self.current is not None:
            atr = float(self.current.get("atr", 0.0) or 0.0)
            stop_distance = atr * self.atr_multiplier
            if stop_distance > 0:
                risk_budget = equity * self.max_risk_per_trade_pct
                return min(risk_budget / stop_distance, notional_cap)
        return notional_cap

    def risk_levels(self, entry: float) -> tuple[float, float]:
        if self.current is None:
            raise ValueError("Strategy has no active candle")
        risk = float(self.current["atr"]) * self.atr_multiplier
        stop_loss = entry - risk
        take_profit = entry + (risk * self.reward_risk)
        return stop_loss, take_profit


class MomentumBreakoutBacktestStrategy(BaseStrategy):
    """Backtest adapter for the live ``momentum_breakout_v1`` strategy.

    Mirrors ``app.services.strategy.momentum_breakout.MomentumBreakoutStrategy``
    so a walk-forward run tagged ``momentum_breakout_v1`` actually validates the
    strategy that trades live — closing the "validated strategy != traded
    strategy" gap. LONG-only here because the backtest engine is long-only
    (short support requires an engine refactor); the short side is noted as a
    TODO and the long signals are the dominant edge for this breakout strategy.

    Entry (LONG): fast EMA > slow EMA, price > trend EMA, close breaks above
    the prior N-bar high (Donchian) by an ATR buffer, volume expands >=
    vol_spike_mult, ATR/price >= min_atr_pct, RSI < rsi_long_max.
    """

    def __init__(self, parameters: dict | None = None) -> None:
        params = parameters or {}
        self.ema_fast = int(params.get("ema_fast", 9))
        self.ema_slow = int(params.get("ema_slow", 21))
        self.ema_trend = int(params.get("ema_trend", 50))
        self.donchian_lookback = int(params.get("donchian_lookback", 20))
        self.vol_spike_mult = float(params.get("vol_spike_mult", 1.3))
        self.rsi_long_max = float(params.get("rsi_long_max", 80.0))
        # Default 0.004 matches the live config (momentum_min_atr_pct). The old
        # 0.0015 default was below the typical round-trip cost — the backtest
        # fired breakouts live rejects.
        self.min_atr_pct = float(params.get("min_atr_pct", 0.004))
        self.breakout_buffer_atr = float(params.get("breakout_buffer_atr", 0.05))
        self.atr_period = int(params.get("atr_period", 14))
        self.atr_multiplier = float(params.get("atr_multiplier", 2.0))
        self.reward_risk = float(params.get("reward_risk", 1.5))
        self.max_capital_per_trade_pct = float(params.get("max_capital_per_trade_pct", 0.05))
        self.max_risk_per_trade_pct = float(params.get("max_risk_per_trade_pct", 0.02))
        # Cost floor for the breakout buffer — mirrors the live strategy so the
        # backtest does not fire breakouts inside the fee+spread+slippage band
        # that live rejects. Default matches momentum_round_trip_cost_pct.
        self.round_trip_cost_pct = float(params.get("round_trip_cost_pct", 0.0022))
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["ema_fast"] = _ema_sma_seed(frame["close"], self.ema_fast)
        frame["ema_slow"] = _ema_sma_seed(frame["close"], self.ema_slow)
        frame["ema_trend"] = _ema_sma_seed(frame["close"], self.ema_trend)
        # RSI(14) — Wilder smoothing (EWM alpha=1/14) matching live indicators.rsi()
        delta = frame["close"].diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs = gain / loss.replace(0, pd.NA)
        frame["rsi"] = 100 - (100 / (1 + rs))
        # ATR
        tr = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - frame["close"].shift()).abs(),
                (frame["low"] - frame["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr"] = tr.rolling(self.atr_period).mean()
        # Donchian channel: prior N-bar high/low EXCLUDING the forming bar.
        frame["donchian_high"] = frame["high"].rolling(self.donchian_lookback).max().shift(1)
        frame["donchian_low"] = frame["low"].rolling(self.donchian_lookback).min().shift(1)
        # Volume expansion: current volume / 20-bar mean volume.
        frame["vol_mean_20"] = frame["volume"].rolling(20).mean()
        frame["vol_ratio"] = frame["volume"] / frame["vol_mean_20"].replace(0, np.nan)
        return frame.dropna()

    def on_candle(self, candle: pd.Series) -> None:
        self.current = candle

    def should_buy(self) -> bool:
        if self.current is None:
            return False
        c = self.current
        price = float(c["close"])
        ema_f = float(c["ema_fast"])
        ema_s = float(c["ema_slow"])
        ema_t = float(c["ema_trend"])
        if ema_t <= 0:
            return False
        # Up momentum: fast > slow and price above trend EMA.
        if not (ema_f > ema_s and price > ema_t):
            return False
        atr_v = float(c.get("atr", 0.0) or 0.0)
        if atr_v <= 0:
            return False
        # Volatility floor: ATR/price must clear costs.
        if (atr_v / price) < self.min_atr_pct:
            return False
        # Volume expansion.
        vol_ratio = float(c.get("vol_ratio", 0.0) or 0.0)
        if vol_ratio < self.vol_spike_mult:
            return False
        # Donchian breakout with ATR buffer, floored at the round-trip cost
        # (matches the live strategy — a breakout inside the fee+spread+slippage
        # band is instantly underwater and must not fire).
        window_high = float(c.get("donchian_high", 0.0) or 0.0)
        atr_buffer = atr_v * self.breakout_buffer_atr
        cost_buffer = price * self.round_trip_cost_pct
        buffer = max(atr_buffer, cost_buffer)
        if price <= (window_high + buffer):
            return False
        # RSI not already exhausted.
        rsi_v = float(c.get("rsi", 50.0) or 50.0)
        if rsi_v >= self.rsi_long_max:
            return False
        return True

    def should_sell(self) -> bool:
        return False

    def position_size(self, equity: float, price: float) -> float:
        if price <= 0:
            return 0.0
        notional_cap = (equity * self.max_capital_per_trade_pct) / price
        if self.current is not None:
            atr_v = float(self.current.get("atr", 0.0) or 0.0)
            stop_distance = atr_v * self.atr_multiplier
            if stop_distance > 0:
                risk_budget = equity * self.max_risk_per_trade_pct
                return min(risk_budget / stop_distance, notional_cap)
        return notional_cap

    def risk_levels(self, entry: float) -> tuple[float, float]:
        if self.current is None:
            raise ValueError("Strategy has no active candle")
        risk = float(self.current["atr"]) * self.atr_multiplier
        stop_loss = entry - risk
        # Trend-following: no fixed take-profit (let winners run via trailing +
        # breakeven, matching the live momentum strategy's expectancy_type="trend").
        # A fixed R:R TP cuts the fat right tail that is the strategy's main edge.
        take_profit = 0.0
        return stop_loss, take_profit


class CapitalPreservationBacktestStrategy(EmaRsiAtrStrategy):
    """Backtest adapter for the live ``capital_preservation_v1`` strategy.

    Subclasses EmaRsiAtrStrategy (same EMA200 trend + RSI oversold + EMA20
    distance gate) but adds the live strategy's additional filters:
    - 24h range filter (block when excessive volatility)
    - Volume expansion filter (block on low volume)
    - Trend tolerance (allow price slightly below EMA200 for LONG)
    """

    name: str = "capital_preservation_v1"

    def __init__(self, parameters: dict | None = None) -> None:
        super().__init__(parameters)
        params = parameters or {}
        self.max_24h_range_pct = float(params.get("max_24h_range_pct", 0.10))
        self.daily_range_candles = int(params.get("daily_range_candles", 12))
        self.min_volume_ratio = float(params.get("min_volume_ratio", 0.6))
        self.trend_tolerance_pct = float(params.get("trend_tolerance_pct", 0.0))

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = super().prepare(data)
        # 24h range: max-min of last N closes / current price
        n = min(self.daily_range_candles, len(frame))
        frame["range_high"] = frame["close"].rolling(n).max()
        frame["range_low"] = frame["close"].rolling(n).min()
        frame["range_pct"] = (frame["range_high"] - frame["range_low"]) / frame["close"]
        # Volume ratio: current volume / 20-bar mean volume
        frame["vol_mean_20"] = frame["volume"].rolling(20).mean()
        frame["vol_ratio"] = frame["volume"] / frame["vol_mean_20"].replace(0, np.nan)
        return frame.dropna()

    def should_buy(self) -> bool:
        if self.current is None:
            return False
        price = float(self.current["close"])
        ema_trend = float(self.current["ema_trend"])
        rsi = float(self.current.get("rsi", 50))
        # Trend tolerance: allow price slightly below EMA200 (like live)
        long_trend_ok = price > ema_trend * (1 - self.trend_tolerance_pct)
        if not long_trend_ok:
            return False
        if rsi >= self.rsi_threshold:
            return False
        # EMA20 distance gate (inherited from EmaRsiAtrStrategy)
        ema_entry = float(self.current.get("ema_entry", 0))
        if ema_entry <= 0:
            return False
        distance = abs(price - ema_entry) / ema_entry
        if distance > self.ema_entry_distance_pct:
            return False
        # 24h range filter
        range_pct = float(self.current.get("range_pct", 0) or 0)
        if range_pct > self.max_24h_range_pct:
            return False
        # Volume filter
        vol_ratio = float(self.current.get("vol_ratio", 0) or 0)
        if vol_ratio < self.min_volume_ratio:
            return False
        return True
