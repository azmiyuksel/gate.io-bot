import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from typing import List, Tuple, Any

from app.strategy_health.statistical_tests import loss_streak_pvalue


class StrategyAnomalyDetector:
    def __init__(self) -> None:
        self.iso_forest = IsolationForest(n_estimators=50, contamination=0.05, random_state=42)
        self.is_fitted = False

    def detect_anomalies(self, trades: List[Any]) -> Tuple[bool, str]:
        """
        Detects performance anomalies using IsolationForest and statistical Z-scores.
        Returns: (is_anomalous, reason)
        """
        if len(trades) < 5:
            return False, "insufficient_data"

        pnls = [float(getattr(t, "realized_pnl", 0.0) or getattr(t, "pnl", 0.0) or t.get("realized_pnl", 0.0) or t.get("pnl", 0.0)) for t in trades]
        
        # 1. Z-Score Anomaly check on PnL
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        
        if std_pnl > 0:
            latest_pnl = pnls[-1]
            z_score = (latest_pnl - mean_pnl) / std_pnl
            
            # Anomalous large loss (Z-score < -3.0)
            if z_score < -3.0:
                return True, f"extreme_loss_anomaly (Z-score: {z_score:.2f})"

        # 2. Loss Streak check (consecutive losses)
        consecutive_losses = 0
        for pnl in reversed(pnls):
            if pnl < 0:
                consecutive_losses += 1
            else:
                break
        
        if consecutive_losses >= 6:
            return True, f"critical_loss_streak ({consecutive_losses} consecutive losses)"

        # Adaptive: flag a shorter streak when it is statistically improbable for
        # this strategy's win rate (a 4-loss run is a red flag at 70% win rate,
        # but normal at 45%). p = loss_rate ** streak.
        if consecutive_losses >= 4:
            win_rate = len([p for p in pnls if p > 0]) / len(pnls)
            p_value = loss_streak_pvalue(consecutive_losses, 1.0 - win_rate)
            if 0 < p_value < 0.01:
                return True, (
                    f"improbable_loss_streak ({consecutive_losses} losses, p={p_value:.3f})"
                )

        # 3. Isolation Forest check (requires at least 20 trades)
        if len(trades) >= 20:
            # Build dataset: [pnl, rolling winrate, rolling drawdown]
            data = []
            for i in range(10, len(pnls)):
                sub_pnls = pnls[:i]
                wins = len([p for p in sub_pnls if p > 0])
                win_rate = wins / len(sub_pnls)
                data.append([pnls[i], win_rate])

            df = pd.DataFrame(data, columns=["pnl", "win_rate"])
            
            try:
                self.iso_forest.fit(df)
                self.is_fitted = True
                
                # Predict latest trade
                latest_features = [[pnls[-1], len([p for p in pnls if p > 0]) / len(pnls)]]
                pred = self.iso_forest.predict(latest_features)[0]
                
                if pred == -1:
                    return True, "isolation_forest_anomaly_detected"
            except Exception:
                # Silently catch fit errors and skip IsolationForest
                pass

        return False, "normal"
