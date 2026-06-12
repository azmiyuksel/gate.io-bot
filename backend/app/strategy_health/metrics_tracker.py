import math
from typing import Dict, List, Any


class StrategyMetricsTracker:
    @staticmethod
    def calculate_rolling_metrics(trades: List[Any], window: int = 50, initial_equity: float = 10000.0) -> Dict[str, float]:
        """
        Calculates rolling metrics on the last N trades.
        """
        recent = trades[-window:] if len(trades) > window else trades
        if not recent:
            return {
                "sharpe": 0.0,
                "win_rate": 0.0,
                "profit_factor": 1.0,
                "drawdown": 0.0,
                "expectancy": 0.0
            }

        pnls = []
        for t in recent:
            val = None
            if hasattr(t, "realized_pnl") and getattr(t, "realized_pnl") is not None:
                val = getattr(t, "realized_pnl")
            elif hasattr(t, "pnl") and getattr(t, "pnl") is not None:
                val = getattr(t, "pnl")
            elif isinstance(t, dict):
                val = t.get("realized_pnl") if t.get("realized_pnl") is not None else t.get("pnl", 0.0)
            pnls.append(float(val if val is not None else 0.0))
        
        # 1. Win Rate
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls) if pnls else 0.0

        # 2. Profit Factor
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

        # 3. Expectancy
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses)) / len(losses) if losses else 0.0
        expectancy = (avg_win * win_rate) - (avg_loss * (1.0 - win_rate))

        # 4. Rolling Sharpe (using daily returns or simple PnL ratio)
        avg_pnl = sum(pnls) / len(pnls)
        if len(pnls) > 1:
            variance = sum((p - avg_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
            std_dev = math.sqrt(variance)
        else:
            std_dev = 0.0
        
        sharpe = (avg_pnl / std_dev) * math.sqrt(252) if std_dev > 0 else 0.0

        # 5. Drawdown from equity peaks of this sequence
        equity = initial_equity
        equity_curve = [equity]
        for p in pnls:
            equity += p
            equity_curve.append(equity)
            
        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        return {
            "sharpe": float(sharpe),
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "drawdown": float(max_dd),
            "expectancy": float(expectancy)
        }

    @staticmethod
    def calculate_streaks(trades: List[Any]) -> Dict[str, int]:
        pnls = []
        for t in trades:
            val = None
            if hasattr(t, "realized_pnl") and getattr(t, "realized_pnl") is not None:
                val = getattr(t, "realized_pnl")
            elif hasattr(t, "pnl") and getattr(t, "pnl") is not None:
                val = getattr(t, "pnl")
            elif isinstance(t, dict):
                val = t.get("realized_pnl") if t.get("realized_pnl") is not None else t.get("pnl", 0.0)
            pnls.append(float(val if val is not None else 0.0))
        
        max_win_streak = 0
        max_loss_streak = 0
        curr_win_streak = 0
        curr_loss_streak = 0

        for p in pnls:
            if p > 0:
                curr_win_streak += 1
                curr_loss_streak = 0
                if curr_win_streak > max_win_streak:
                    max_win_streak = curr_win_streak
            elif p < 0:
                curr_loss_streak += 1
                curr_win_streak = 0
                if curr_loss_streak > max_loss_streak:
                    max_loss_streak = curr_loss_streak
            else:
                curr_win_streak = 0
                curr_loss_streak = 0

        return {
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "current_win_streak": curr_win_streak,
            "current_loss_streak": curr_loss_streak
        }
