"""Pattern mining over trades, regime performance and successful strategies.

Produces a pattern catalogue (e.g. "strategy X performs best in BULL regime",
"winning trades cluster around ...") and records each finding in the knowledge
base for downstream evolution and reporting.
"""
from __future__ import annotations

import statistics

from sqlalchemy.orm import Session

from app.auto_learning.knowledge_base import KnowledgeBase
from app.auto_learning.models import KnowledgeType, PatternFinding
from app.models.entities import StrategyVersion


class PatternMiner:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.kb = KnowledgeBase(db)

    def mine(self, symbol: str = "BTC_USDT", cycle_id: int | None = None) -> list[PatternFinding]:
        findings: list[PatternFinding] = []
        findings += self._trade_patterns(symbol, cycle_id)
        findings += self._regime_patterns(symbol, cycle_id)
        findings += self._parameter_patterns(symbol, cycle_id)
        return findings

    # --- successful vs failing trade sets ---
    def _trade_patterns(self, symbol: str, cycle_id: int | None) -> list[PatternFinding]:
        trades = self.kb.closed_trades(limit=2000)
        pnls = [float(t.realized_pnl) for t in trades]
        if len(pnls) < 10:
            return []
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        win_rate = len(wins) / len(pnls)
        avg_win = statistics.fmean(wins) if wins else 0.0
        avg_loss = statistics.fmean(losses) if losses else 0.0

        finding = PatternFinding(
            title="Trade outcome distribution",
            description=(
                f"{len(pnls)} closed trades: win-rate {win_rate:.1%}, "
                f"avg win {avg_win:.2f}, avg loss {avg_loss:.2f}, "
                f"reward/risk {abs(avg_win / avg_loss):.2f}" if avg_loss else f"win-rate {win_rate:.1%}"
            ),
            support=len(pnls),
            win_rate=round(win_rate, 4),
            avg_pnl=round(statistics.fmean(pnls), 4),
        )
        self.kb.record(
            KnowledgeType.pattern, finding.title, finding.description,
            symbol=symbol, confidence=min(1.0, len(pnls) / 200),
            support=len(pnls), cycle_id=cycle_id,
            payload={"win_rate": win_rate, "avg_win": avg_win, "avg_loss": avg_loss},
        )
        return [finding]

    # --- regime-based performance ---
    def _regime_patterns(self, symbol: str, cycle_id: int | None) -> list[PatternFinding]:
        rows = self.kb.regime_performance()
        if not rows:
            return []
        best_by_regime: dict[str, object] = {}
        for row in rows:
            cur = best_by_regime.get(row.regime_type)
            if cur is None or float(row.profit_factor) > float(cur.profit_factor):
                best_by_regime[row.regime_type] = row

        findings = []
        for regime, row in best_by_regime.items():
            wr = (row.winning_trades / row.total_trades) if row.total_trades else 0.0
            desc = (
                f"In {regime}, '{row.strategy_name}' leads with profit factor "
                f"{float(row.profit_factor):.2f} over {row.total_trades} trades"
            )
            findings.append(
                PatternFinding(title=f"Best strategy in {regime}", description=desc,
                               support=row.total_trades, win_rate=round(wr, 4),
                               avg_pnl=float(row.total_pnl), regime=regime)
            )
            self.kb.record(
                KnowledgeType.regime, f"Best strategy in {regime}", desc,
                symbol=symbol, regime=regime,
                confidence=min(1.0, (row.total_trades or 0) / 50),
                support=row.total_trades, cycle_id=cycle_id,
                payload={"strategy": row.strategy_name, "profit_factor": float(row.profit_factor)},
            )
        return findings

    # --- parameter regions of successful strategies ---
    def _parameter_patterns(self, symbol: str, cycle_id: int | None) -> list[PatternFinding]:
        winners = (
            self.db.query(StrategyVersion)
            .filter(StrategyVersion.overfit.is_(False))
            .filter(StrategyVersion.sharpe > 0)
            .order_by(StrategyVersion.fitness.desc())
            .limit(20)
            .all()
        )
        if len(winners) < 5:
            return []
        keys = ["ema_trend", "rsi_threshold", "atr_multiplier", "reward_risk"]
        medians = {}
        for key in keys:
            values = [float(v.parameters.get(key)) for v in winners if v.parameters.get(key) is not None]
            if values:
                medians[key] = round(statistics.median(values), 4)
        if not medians:
            return []
        desc = "Top strategies cluster around " + ", ".join(f"{k}≈{v}" for k, v in medians.items())
        finding = PatternFinding(
            title="Successful parameter region", description=desc,
            support=len(winners), win_rate=0.0, avg_pnl=0.0,
        )
        self.kb.record(
            KnowledgeType.meta, finding.title, desc, symbol=symbol,
            confidence=min(1.0, len(winners) / 20), support=len(winners),
            cycle_id=cycle_id, payload={"medians": medians},
        )
        return [finding]
