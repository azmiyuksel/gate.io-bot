from decimal import Decimal
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import HistoricalCandle


class CorrelationEngine:
    def __init__(self, db: Session) -> None:
        self.db = db

    def calculate_correlation(self, symbols: list[str], timeframe: str = "1h", limit: int = 100) -> dict:
        """
        Calculates rolling correlation matrix for given symbols based on historical candles.
        """
        if len(symbols) < 2:
            # Return identity matrix for single asset
            return {
                "matrix": {s: {s: 1.0} for s in symbols},
                "high_correlation_pairs": [],
                "risk_score": 0.0
            }

        data = {}
        for symbol in symbols:
            candles = (
                self.db.query(HistoricalCandle)
                .filter(HistoricalCandle.symbol == symbol, HistoricalCandle.timeframe == timeframe)
                .order_by(HistoricalCandle.timestamp.desc())
                .limit(limit)
                .all()
            )
            if len(candles) >= 10:
                # Reverse to chronological order
                data[symbol] = pd.Series(
                    [float(c.close) for c in candles[::-1]],
                    index=[c.timestamp for c in candles[::-1]]
                )

        if not data:
            # Return dummy matrix if no data is found
            return {
                "matrix": {s1: {s2: 0.5 if s1 != s2 else 1.0 for s2 in symbols} for s1 in symbols},
                "high_correlation_pairs": [],
                "risk_score": 0.0
            }

        # Align series into a DataFrame
        df = pd.DataFrame(data).ffill().bfill()
        
        # Calculate correlation matrix
        corr_matrix = df.corr(method="pearson").fillna(0.0)
        
        matrix_dict = corr_matrix.to_dict()
        
        # Find high correlation pairs (> 0.8)
        high_corr = []
        corr_values = []
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                s1, s2 = symbols[i], symbols[j]
                if s1 in matrix_dict and s2 in matrix_dict[s1]:
                    val = matrix_dict[s1][s2]
                    corr_values.append(val)
                    if val > 0.8:
                        high_corr.append((s1, s2, val))
        
        # Risk score based on average positive correlation
        avg_corr = np.mean([v for v in corr_values if v > 0]) if corr_values else 0.0
        risk_score = float(max(0.0, min(1.0, avg_corr)))

        return {
            "matrix": matrix_dict,
            "high_correlation_pairs": high_corr,
            "risk_score": risk_score
        }
