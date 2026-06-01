import pandas as pd
from app.models.enums import MarketRegimeType
from app.market_regime.classifier import RandomForestRegimeClassifier
from app.market_regime.clustering import KMeansRegimeClustering
from app.market_regime.models import WEIGHT_CLUSTERING, WEIGHT_ML, WEIGHT_RULE_BASED
from app.market_regime.trend import TrendClassifier
from app.market_regime.volatility import VolatilityClassifier


class MarketRegimeDetector:
    def __init__(self) -> None:
        self.clustering = KMeansRegimeClustering()
        self.classifier = RandomForestRegimeClassifier()
        self.df_stats = {}

    def fit_detectors(self, df: pd.DataFrame) -> None:
        """
        Fits K-Means clustering and Random Forest classifier on historical feature DataFrame.
        """
        if len(df) < 50:
            return

        # Record mean & std statistics for future normalization
        features = [
            "ema_200_slope", "adx", "bb_width", "realized_vol", 
            "rsi", "roc", "volume_spike", "obv_slope"
        ]
        for feat in features:
            self.df_stats[f"{feat}_mean"] = float(df[feat].mean())
            self.df_stats[f"{feat}_std"] = float(df[feat].std())

        # Fit K-Means
        self.clustering.fit(df)
        
        # Fit Random Forest
        self.classifier.train(df)

    def detect(self, row: pd.Series) -> tuple[MarketRegimeType, float, dict]:
        """
        Combines the outputs of Rule-Based, Clustering, and ML models into an ensemble vote.
        Returns: (consensus_regime, confidence_score, votes_dict)
        """
        row_dict = row.to_dict()
        
        # 1. Rule-Based Vote
        trend_reg = TrendClassifier.classify_trend(row_dict)
        vol_reg = VolatilityClassifier.classify_volatility(row_dict)
        
        # Volatility overrides trend in rule-based
        if vol_reg in (MarketRegimeType.high_volatility, MarketRegimeType.low_volatility, MarketRegimeType.breakout_phase):
            vote_rule = vol_reg
        else:
            vote_rule = trend_reg

        # 2. Clustering Vote
        vote_cluster = self.clustering.predict(row, self.df_stats)

        # 3. ML Classifier Vote
        vote_ml = self.classifier.predict(row)

        # Calculate weighted votes
        votes = {
            MarketRegimeType.trending_bull: 0.0,
            MarketRegimeType.trending_bear: 0.0,
            MarketRegimeType.sideways: 0.0,
            MarketRegimeType.high_volatility: 0.0,
            MarketRegimeType.low_volatility: 0.0,
            MarketRegimeType.breakout_phase: 0.0,
        }

        votes[vote_rule] += WEIGHT_RULE_BASED
        votes[vote_cluster] += WEIGHT_CLUSTERING
        votes[vote_ml] += WEIGHT_ML

        # Find consensus
        consensus_regime = max(votes, key=votes.get)
        confidence = votes[consensus_regime]

        votes_str = {
            "rule_based": vote_rule.value,
            "clustering": vote_cluster.value,
            "ml_model": vote_ml.value
        }

        return consensus_regime, confidence, votes_str
