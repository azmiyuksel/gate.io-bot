from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from app.account.engine import AccountManager
from app.api.deps import CurrentUser, DbSession, current_user_role, require_admin
from app.core.audit import record_audit
from app.core.config import get_settings
from app.models.entities import AuditLog, HistoricalCandle, Position, Trade
from app.models.enums import PositionStatus
from app.repositories.trading import (
    PositionRepository,
    StrategySettingsRepository,
    TradeRepository,
)
from app.schemas.dashboard import DashboardSummary, StrategySettingsUpdate
from app.services.analytics.economics import (
    benchmark_comparison,
    hurdle_comparison,
    trade_economics,
)
from app.services.exchange.gateio import GateIOClient
from app.services.trading_engine import TradingEngine

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(current_user_role)])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: DbSession) -> DashboardSummary:
    positions = PositionRepository(db)
    trades = TradeRepository(db)
    settings = StrategySettingsRepository(db).current()
    recent_trades = db.query(Trade).order_by(Trade.traded_at.desc()).limit(20).all()
    return DashboardSummary(
        total_balance=AccountManager(db).latest_equity(),
        daily_pnl=trades.daily_pnl(),
        weekly_pnl=trades.weekly_pnl(),
        bot_enabled=settings.is_enabled,
        open_positions=positions.open_positions(),
        recent_trades=recent_trades,
        strategy=settings,
    )


@router.get("/charts")
def charts(db: DbSession) -> dict:
    trades = db.query(Trade).order_by(Trade.traded_at.asc()).all()
    equity = Decimal("0")
    points = []
    wins = 0
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    daily: dict[str, Decimal] = {}
    for trade in trades:
        equity += trade.realized_pnl
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
        wins += int(trade.realized_pnl > 0)
        day = trade.traded_at.date().isoformat()
        daily[day] = daily.get(day, Decimal("0")) + trade.realized_pnl
        points.append({"date": trade.traded_at.isoformat(), "equity": float(equity)})
    win_rate = (wins / len(trades)) * 100 if trades else 0
    daily_pnl = [{"date": day, "pnl": float(pnl)} for day, pnl in sorted(daily.items())]
    return {
        "equity_curve": points,
        "daily_pnl": daily_pnl,
        "monthly_pnl": [],
        "win_rate": win_rate,
        "max_drawdown": float(max_drawdown),
    }


@router.get("/audit", dependencies=[Depends(require_admin)])
def audit_log(db: DbSession, limit: int = 100) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/economics")
def economics(db: DbSession) -> dict:
    """Trade-economics edge report + buy-and-hold (BTC) benchmark.

    Answers: is expected value per trade positive, does the realized win rate
    clear break-even, and does the strategy beat simply holding the asset?
    """
    trades = db.query(Trade).order_by(Trade.traded_at.asc()).all()
    pnls = [float(t.realized_pnl) for t in trades]
    edge = trade_economics(pnls)

    # Strategy return over the window, relative to the capital it started from.
    total_pnl = sum(pnls)
    equity = float(AccountManager(db).latest_equity())
    starting_capital = equity - total_pnl
    strategy_return = total_pnl / starting_capital if starting_capital > 0 else 0.0

    # Benchmark: buy-and-hold the primary symbol over the same trade window.
    settings = get_settings()
    symbol = settings.symbols[0] if settings.symbols else "BTC_USDT"
    benchmark = {"strategy_return": strategy_return, "benchmark_return": 0.0,
                 "excess_return": strategy_return, "outperforms": strategy_return > 0}
    if trades:
        candles = (
            db.query(HistoricalCandle)
            .filter(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.timeframe == settings.market_data_interval,
                HistoricalCandle.timestamp >= trades[0].traded_at,
                HistoricalCandle.timestamp <= trades[-1].traded_at,
            )
            .order_by(HistoricalCandle.timestamp.asc())
            .all()
        )
        closes = [float(c.close) for c in candles]
        if len(closes) >= 2:
            benchmark = benchmark_comparison(strategy_return, closes)
    benchmark["benchmark_symbol"] = symbol

    # Opportunity cost: did the strategy beat what idle capital could have earned?
    period_days = (trades[-1].traded_at - trades[0].traded_at).days if trades else 0
    hurdle = hurdle_comparison(strategy_return, settings.annual_risk_free_rate, period_days)
    return {"edge": edge, "benchmark": benchmark, "hurdle": hurdle}


@router.patch("/strategy", dependencies=[Depends(require_admin)])
def update_strategy(payload: StrategySettingsUpdate, db: DbSession, user: CurrentUser) -> dict:
    settings = StrategySettingsRepository(db).current()
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(settings, key, value)
    settings.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(settings)
    record_audit(db, user.email, "strategy.update", str(changes))
    return {"status": "updated", "strategy": settings}


@router.post("/positions/{position_id}/close", dependencies=[Depends(require_admin)])
async def close_position(position_id: int, db: DbSession, user: CurrentUser) -> dict:
    position = db.get(Position, position_id)
    if position is None or position.status != PositionStatus.open:
        raise HTTPException(status_code=404, detail="Open position not found")
    client = GateIOClient()
    try:
        engine = TradingEngine(db, client)
        order = await engine.close_position(position, reason="manual_close")
        record_audit(db, user.email, "position.close", f"position_id={position_id}")
        return {"status": "closing", "order_id": order.id}
    finally:
        await client.close()
