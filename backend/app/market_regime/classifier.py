import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from app.models.enums import MarketRegimeType
from app.market_regime.trend import TrendClassifier
from app.market_regime.volatility import VolatilityClassifier


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
        """
        Generates silver labels using the rule-based trend and volatility classifiers.
        """
        labels = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            trend = TrendClassifier.classify_trend(row_dict)
            vol = VolatilityClassifier.classify_volatility(row_dict)
            
            # Combine logic: if volatile/breakout, override trend
            if vol in (MarketRegimeType.high_volatility, MarketRegimeType.low_volatility, MarketRegimeType.breakout_phase):
                labels.append(vol.value)
            else:
                labels.append(trend.value)
        return pd.Series(labels)

    def train(self, df: pd.DataFrame) -> None:
        """
        Trains the Random Forest model on generated silver labels.
        """
        if len(df) < 50:
            return

        X = df[self.features].fillna(0.0)
        y = self.generate_labels(df)

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
