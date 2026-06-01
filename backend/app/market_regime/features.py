import numpy as np
import pandas as pd


class FeatureEngineer:
    @staticmethod
    def compute_features(candles: list[dict]) -> pd.DataFrame:
        """
        Calculates all features needed for market regime classification.
        Expects a list of candle dictionaries with: open, high, low, close, volume, timestamp.
        """
        if not candles:
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(candles)
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["open"] = df["open"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # 1. Trend Features
        # EMAs
        df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()

        # Slopes (normalized percent change over 3 periods)
        df["ema_20_slope"] = df["ema_20"].pct_change(3)
        df["ema_50_slope"] = df["ema_50"].pct_change(5)
        df["ema_200_slope"] = df["ema_200"].pct_change(10)

        # Price vs EMAs
        df["price_vs_ema20"] = (df["close"] - df["ema_20"]) / df["ema_20"]
        df["price_vs_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"]
        df["price_vs_ema200"] = (df["close"] - df["ema_200"]) / df["ema_200"]

        # Simple ADX calculation
        df["tr"] = np.maximum(
            df["high"] - df["low"],
            np.maximum(
                abs(df["high"] - df["close"].shift(1)),
                abs(df["low"] - df["close"].shift(1))
            )
        )
        df["atr"] = df["tr"].rolling(14).mean()
        
        # Up Move / Down Move
        up_move = df["high"] - df["high"].shift(1)
        down_move = df["low"].shift(1) - df["low"]
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        tr_smooth = df["tr"].rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / tr_smooth)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0.0, 1.0)
        df["adx"] = dx.rolling(14).mean()

        # 2. Volatility Features
        df["bb_mid"] = df["close"].rolling(20).mean()
        df["bb_std"] = df["close"].rolling(20).std()
        df["bb_width"] = (4 * df["bb_std"]) / df["bb_mid"]
        
        # Realized Volatility (std of log returns over 20 periods)
        df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
        df["realized_vol"] = df["log_ret"].rolling(20).std() * np.sqrt(365 * 24) # annualized hourly

        # 3. Momentum Features
        # RSI
        change = df["close"].diff()
        gain = np.where(change > 0, change, 0.0)
        loss = np.where(change < 0, -change, 0.0)
        avg_gain = pd.Series(gain).rolling(14).mean()
        avg_loss = pd.Series(loss).rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0.0, 0.00001)
        df["rsi"] = 100 - (100 / (1.0 + rs))

        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # ROC (Rate of change)
        df["roc"] = df["close"].pct_change(10)

        # 4. Volume Features
        df["volume_ma"] = df["volume"].rolling(20).mean()
        df["volume_spike"] = df["volume"] / df["volume_ma"].replace(0.0, 1.0)

        # OBV
        direction = np.sign(df["close"].diff())
        df["obv"] = (direction * df["volume"]).fillna(0.0).cumsum()
        df["obv_slope"] = df["obv"].pct_change(5)

        # Fill NaNs
        df = df.ffill().bfill().fillna(0.0)

        return df
