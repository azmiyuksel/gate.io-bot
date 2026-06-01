from abc import ABC

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
        return (equity * self.max_capital_per_trade_pct) / price

    def risk_levels(self, entry: float) -> tuple[float, float]:
        if self.current is None:
            raise ValueError("Strategy has no active candle")
        risk = float(self.current["atr"]) * self.atr_multiplier
        stop_loss = entry - risk
        take_profit = entry + (risk * self.reward_risk)
        return stop_loss, take_profit
