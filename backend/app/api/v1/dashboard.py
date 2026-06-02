from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException

from app.account.engine import AccountManager
from app.api.deps import CurrentUser, DbSession, current_user_role, require_admin
from app.core.audit import record_audit
from app.models.entities import AuditLog, Position, Trade
from app.models.enums import PositionStatus
from app.repositories.trading import (
    PositionRepository,
    StrategySettingsRepository,
    TradeRepository,
)
from app.schemas.dashboard import DashboardSummary, StrategySettingsUpdate
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
