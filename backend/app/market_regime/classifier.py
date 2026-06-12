import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from app.models.enums import MarketRegimeType
from app.market_regime.trend import TrendClassifier


class RandomForestRegimeClassifier:
    def __init__(self) -> None:
        self.clf = RandomForestClassifier(n_estimators=100, random_state=42)
        self.is_trained = False
        self.features = [
            "ema_20_slope", "ema_50_slope", "ema_200_slope",
            "price_vs_ema20", "price_vs_ema50", "price_vs_ema200",
            "adx", "bb_width", "realized_vol", "rsi", "roc",
            "volume_spike", "obv_slope"
        ]

    def generate_labels(self, df: pd.DataFrame) -> pd.Series:
        """Generate labels from forward returns instead of rule-based pseudo-labels.

        This avoids circular reasoning where the ML model only learns what the
        rule-based classifiers already know.  Forward returns provide genuine
        ground-truth signal about which regime the market was actually in.

        Binning strategy (5 classes):
            top 20% returns  → trending_bull
            bottom 20%       → trending_bear
            high vol quartile with small return → high_volatility
            low vol quartile with small return  → low_volatility
            everything else  → sideways
        """
        if "close" not in df.columns:
            return pd.Series(["sideways"] * len(df))

        forward_return = df["close"].pct_change().shift(-1)

        # Use the same forward return for the current bar's features
        labels = []
        for i in range(len(df)):
            fwd = forward_return.iloc[i]

            if np.isnan(fwd):
                labels.append(MarketRegimeType.sideways.value)
                continue

            ret_percentile = forward_return.rank(pct=True).iloc[i]
            vol_percentile = df["realized_vol"].rank(pct=True).iloc[i] if "realized_vol" in df.columns else 0.5

            if ret_percentile >= 0.80:
                labels.append(MarketRegimeType.trending_bull.value)
            elif ret_percentile <= 0.20:
                labels.append(MarketRegimeType.trending_bear.value)
            elif vol_percentile >= 0.75 and abs(fwd) < 0.005:
                labels.append(MarketRegimeType.high_volatility.value)
            elif vol_percentile <= 0.25 and abs(fwd) < 0.005:
                labels.append(MarketRegimeType.low_volatility.value)
            else:
                labels.append(MarketRegimeType.sideways.value)

        return pd.Series(labels)

    def train(self, df: pd.DataFrame) -> None:
        """
        Trains the Random Forest model on forward-return based labels.
        """
        if len(df) < 50:
            return

        X = df[self.features].fillna(0.0)
        y = self.generate_labels(df)

        # Skip if only one class present (can't train binary/multi-class)
        if len(y.unique()) < 2:
            return

        self.clf.fit(X, y)
        self.is_trained = True

    def predict(self, row: pd.Series) -> MarketRegimeType:
        """
        Predicts the market regime for a single feature vector.
        """
        if not self.is_trained:
            # Fallback to trend rule-based classification if classifier is not trained
            return TrendClassifier.classify_trend(row.to_dict())

        X_test = pd.DataFrame([row[self.features].fillna(0.0)])
        pred = self.clf.predict(X_test)[0]
        return MarketRegimeType(pred)
