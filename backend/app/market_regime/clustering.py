import pandas as pd
from sklearn.cluster import KMeans
from app.models.enums import MarketRegimeType


class KMeansRegimeClustering:
    def __init__(self, n_clusters: int = 5) -> None:
        self.n_clusters = n_clusters
        self.kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        self.cluster_map = {}  # maps cluster_id -> MarketRegimeType

    def fit(self, df: pd.DataFrame) -> None:
        """
        Fits KMeans on the feature space and maps clusters to regimes.
        """
        if len(df) < self.n_clusters:
            return

        features = [
            "ema_200_slope", "adx", "bb_width", "realized_vol", 
            "rsi", "roc", "volume_spike", "obv_slope"
        ]
        
        # Standardize features (simple division/z-score)
        X = df[features].fillna(0.0)
        X_norm = (X - X.mean()) / X.std().replace(0.0, 1.0)

        self.kmeans.fit(X_norm)
        
        # Map clusters to regimes by analyzing centroids
        centroids = self.kmeans.cluster_centers_
        
        # Centroid dimensions map to features index
        # 0: ema_200_slope
        # 1: adx
        # 2: bb_width
        # 3: realized_vol
        # 4: rsi
        # 5: roc
        
        for cluster_id in range(self.n_clusters):
            centroid = centroids[cluster_id]
            slope = centroid[0]
            adx = centroid[1]
            bb_width = centroid[2]
            vol = centroid[3]
            rsi_val = centroid[4]
            roc = centroid[5]

            # Heuristics to assign regime label to cluster id
            if vol > 1.2 or bb_width > 1.2:
                self.cluster_map[cluster_id] = MarketRegimeType.high_volatility
            elif vol < -0.8 or bb_width < -0.8:
                self.cluster_map[cluster_id] = MarketRegimeType.low_volatility
            elif slope > 0.5 and adx > 0.5:
                self.cluster_map[cluster_id] = MarketRegimeType.trending_bull
            elif slope < -0.5 and adx > 0.5:
                self.cluster_map[cluster_id] = MarketRegimeType.trending_bear
            elif abs(slope) > 0.5 and bb_width > 0.5:
                self.cluster_map[cluster_id] = MarketRegimeType.breakout_phase
            else:
                self.cluster_map[cluster_id] = MarketRegimeType.sideways

    def predict(self, row: pd.Series, df_stats: dict) -> MarketRegimeType:
        """
        Predicts the regime for a single row based on fitted clusters.
        """
        if not self.cluster_map:
            return MarketRegimeType.sideways

        features = [
            "ema_200_slope", "adx", "bb_width", "realized_vol", 
            "rsi", "roc", "volume_spike", "obv_slope"
        ]
        
        # Normalize row
        row_norm = []
        for feat in features:
            val = float(row.get(feat, 0.0))
            mean = df_stats.get(f"{feat}_mean", 0.0)
            std = df_stats.get(f"{feat}_std", 1.0)
            row_norm.append((val - mean) / (std if std != 0 else 1.0))
            
        cluster_id = self.kmeans.predict([row_norm])[0]
        return self.cluster_map.get(cluster_id, MarketRegimeType.sideways)
