from abc import ABC

import numpy as np
import pandas as pd


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
        ema_fast = frame["close"].ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = frame["close"].ewm(span=self.macd_slow, adjust=False).mean()
        frame["macd"] = ema_fast - ema_slow
        frame["macd_signal_line"] = frame["macd"].ewm(span=self.macd_signal, adjust=False).mean()
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
        return (
            float(self.current.get("macd_histogram", 0)) > 0
            and self.current.name > 0
        )

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
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["bb_mid"] = frame["close"].rolling(self.bb_period).mean()
        bb_std = frame["close"].rolling(self.bb_period).std()
        frame["bb_upper"] = frame["bb_mid"] + self.bb_std * bb_std
        frame["bb_lower"] = frame["bb_mid"] - self.bb_std * bb_std
        frame["bb_width"] = (frame["bb_upper"] - frame["bb_lower"]) / frame["bb_mid"]
        delta = frame["close"].diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
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
        return price <= lower * 1.005 and rsi < self.rsi_oversold

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
        self.current: pd.Series | None = None

    def prepare(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame["ema_trend"] = frame["close"].ewm(span=self.ema_trend, adjust=False).mean()
        frame["ema_entry"] = frame["close"].ewm(span=self.ema_entry, adjust=False).mean()
        delta = frame["close"].diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
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
        return distance <= 0.01

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
