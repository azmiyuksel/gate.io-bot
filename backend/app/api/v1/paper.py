from datetime import UTC, datetime, timedelta
from decimal import Decimal
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade
from app.models.enums import PaperBotStatus
from app.paper_trading.metrics import PaperMetrics
from app.paper_trading.portfolio import PaperPortfolio
from app.schemas.paper import (
    PaperLogOut,
    PaperMetricsOut,
    PaperOrderOut,
    PaperPositionOut,
    PaperRiskStatusOut,
    PaperStartRequest,
    PaperStatus,
    PaperTradeOut,
)
from app.services.analytics.economics import trade_economics

router = APIRouter(prefix="/paper", tags=["paper"], dependencies=[Depends(current_user_role)])


@router.post("/start", dependencies=[Depends(require_admin)])
def start_paper(payload: PaperStartRequest, db: DbSession) -> dict:
    account = _get_or_create_account(db, payload.account_name, payload.initial_balance)
    account.status = PaperBotStatus.running
    # Record initial equity point so the chart is never empty
    portfolio = PaperPortfolio(db, account)
    portfolio.record_equity()
    db.commit()
    return {"status": account.status, "account_id": account.id, "symbols": payload.symbols}


@router.post("/stop", dependencies=[Depends(require_admin)])
def stop_paper(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    account.status = PaperBotStatus.stopped
    db.commit()
    return {"status": account.status, "account_id": account.id}


@router.get("/status", response_model=PaperStatus)
def status(db: DbSession) -> PaperStatus:
    account = _get_or_create_account(db)
    portfolio = PaperPortfolio(db, account)
    open_positions = portfolio.open_positions()
    unrealized = sum((position.unrealized_pnl for position in open_positions), Decimal("0"))
    # Surface WHY the bot paused (e.g. a risk limit auto-pause halts all new entries
    # — "one buy then silence"), so the dashboard can explain the standstill.
    pause_reason = None
    if account.status == PaperBotStatus.paused:
        last_pause = (
            db.query(PaperLog)
            .filter(PaperLog.account_id == account.id, PaperLog.event == "system_paused")
            .order_by(PaperLog.created_at.desc())
            .first()
        )
        pause_reason = last_pause.message if last_pause else None
    return PaperStatus(
        account_id=account.id,
        status=account.status,
        cash_balance=account.cash_balance,
        equity=portfolio.equity(),
        initial_balance=account.initial_balance,
        realized_pnl=account.realized_pnl,
        unrealized_pnl=unrealized,
        exposure=portfolio.exposure_pct(),
        metrics=PaperMetrics(db, account.id).summary(),
        pause_reason=pause_reason,
    )


@router.get("/positions", response_model=list[PaperPositionOut])
def positions(db: DbSession) -> list[PaperPosition]:
    account = _get_or_create_account(db)
    return (
        db.query(PaperPosition)
        .filter(PaperPosition.account_id == account.id, PaperPosition.is_open.is_(True))
        .order_by(PaperPosition.opened_at.desc())
        .all()
    )


@router.get("/trades", response_model=list[PaperTradeOut])
def trades(db: DbSession) -> list[PaperTrade]:
    account = _get_or_create_account(db)
    return (
        db.query(PaperTrade)
        .filter(PaperTrade.account_id == account.id)
        .order_by(PaperTrade.traded_at.desc())
        .limit(100)
        .all()
    )


@router.get("/equity")
def equity(db: DbSession) -> list[dict]:
    account = _get_or_create_account(db)
    points = (
        db.query(PaperEquityCurve)
        .filter(PaperEquityCurve.account_id == account.id)
        .order_by(PaperEquityCurve.timestamp.asc())
        .limit(2000)
        .all()
    )
    return [
        {
            "timestamp": point.timestamp.isoformat(),
            "equity": float(point.equity),
            "drawdown": float(point.drawdown),
            "exposure": float(point.exposure),
        }
        for point in points
    ]


@router.post("/reset", dependencies=[Depends(require_admin)])
def reset(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    db.query(PaperEquityCurve).filter(PaperEquityCurve.account_id == account.id).delete()
    db.query(PaperTrade).filter(PaperTrade.account_id == account.id).delete()
    db.query(PaperPosition).filter(PaperPosition.account_id == account.id).delete()
    account.cash_balance = account.initial_balance
    account.realized_pnl = Decimal("0")
    account.status = PaperBotStatus.stopped
    db.commit()
    return {"status": "reset", "account_id": account.id}


@router.post("/pause", dependencies=[Depends(require_admin)])
def pause_paper(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    account.status = PaperBotStatus.paused
    db.commit()
    return {"status": account.status, "account_id": account.id}


@router.post("/resume", dependencies=[Depends(require_admin)])
def resume_paper(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    account.status = PaperBotStatus.running
    # Record equity point so chart updates immediately
    portfolio = PaperPortfolio(db, account)
    portfolio.record_equity()
    db.commit()
    return {"status": account.status, "account_id": account.id}


@router.get("/orders", response_model=list[PaperOrderOut])
def orders(db: DbSession) -> list[PaperOrder]:
    account = _get_or_create_account(db)
    return (
        db.query(PaperOrder)
        .filter(PaperOrder.account_id == account.id)
        .order_by(PaperOrder.created_at.desc())
        .limit(100)
        .all()
    )


@router.get("/metrics", response_model=PaperMetricsOut)
def metrics(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    return PaperMetrics(db, account.id).summary()


@router.get("/economics")
def economics(db: DbSession) -> dict:
    """Trade-economics edge (expectancy, R-multiple, break-even win rate) plus a
    cost bridge (gross PnL -> fees -> net PnL) so the strategy's real edge after
    costs is visible at a glance."""
    account = _get_or_create_account(db)
    trades = (
        db.query(PaperTrade)
        .filter(PaperTrade.account_id == account.id)
        .order_by(PaperTrade.traded_at.asc())
        .all()
    )
    # Per-trade realized PnL comes from closes (buys carry 0); use those for edge.
    closed_pnls = [float(t.realized_pnl) for t in trades if t.realized_pnl != 0]
    edge = trade_economics(closed_pnls)

    total_fees = float(sum((t.fee for t in trades), Decimal("0")))
    net_pnl = float(account.realized_pnl)
    gross_pnl = net_pnl + total_fees  # net is already fee-deducted
    fee_pct_of_gross = (total_fees / abs(gross_pnl)) if gross_pnl else 0.0
    return {
        "edge": edge,
        "cost_bridge": {
            "gross_pnl": gross_pnl,
            "total_fees": total_fees,
            "net_pnl": net_pnl,
            "fee_pct_of_gross": fee_pct_of_gross,
        },
    }


@router.get("/risk", response_model=PaperRiskStatusOut)
def risk_status(db: DbSession) -> PaperRiskStatusOut:
    account = _get_or_create_account(db)
    portfolio = PaperPortfolio(db, account)
    equity_points = (
        db.query(PaperEquityCurve)
        .filter(PaperEquityCurve.account_id == account.id)
        .order_by(PaperEquityCurve.timestamp.desc())
        .limit(1)
        .all()
    )
    current_dd = abs(float(equity_points[0].drawdown)) if equity_points else 0.0
    equity = portfolio.equity()
    daily_loss = (
        float(max(account.initial_balance - equity, Decimal("0")) / account.initial_balance)
        if account.initial_balance > 0
        else 0.0
    )
    return PaperRiskStatusOut(
        max_daily_loss_pct=float(account.max_daily_loss_pct),
        current_daily_loss_pct=daily_loss,
        max_drawdown_pct=float(account.max_drawdown_pct),
        current_drawdown=current_dd,
        max_exposure_pct=float(account.max_exposure_pct),
        current_exposure=float(portfolio.exposure_pct()),
        max_open_positions=account.max_open_positions,
        current_open_positions=len(portfolio.open_positions()),
        status=account.status,
    )


@router.get("/logs", response_model=list[PaperLogOut])
def logs(db: DbSession) -> list[PaperLog]:
    account = _get_or_create_account(db)
    return (
        db.query(PaperLog)
        .filter(PaperLog.account_id == account.id)
        .order_by(PaperLog.created_at.desc())
        .limit(200)
        .all()
    )


@router.get("/signal-diagnostics")
def signal_diagnostics(db: DbSession, hours: int = 24) -> dict:
    """Aggregate why entries were skipped, so the dashboard can show — live — which
    filter is gating the (deliberately selective) strategy.

    Tallies the per-evaluation `entry_skipped` (strategy filters) and `risk_check`
    (risk-simulator gates / approvals) records over the given window.
    """
    account = _get_or_create_account(db)
    window = max(1, min(int(hours), 168))
    since = datetime.now(UTC) - timedelta(hours=window)
    rows = (
        db.query(PaperLog)
        .filter(
            PaperLog.account_id == account.id,
            PaperLog.event.in_(("entry_skipped", "risk_check")),
            PaperLog.created_at >= since,
        )
        .order_by(PaperLog.created_at.desc())
        .all()
    )
    reason_counts: dict[str, int] = {}
    latest_by_symbol: dict[str, dict] = {}
    total = 0
    last_evaluation_at = rows[0].created_at.isoformat() if rows and rows[0].created_at else None
    for row in rows:
        payload = row.payload or {}
        reason = payload.get("reason") or row.message
        symbol = payload.get("symbol")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        total += 1
        if symbol and symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = {
                "reason": reason,
                "at": row.created_at.isoformat() if row.created_at else None,
            }
    ordered = dict(sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "window_hours": window,
        "evaluations": total,
        "last_evaluation_at": last_evaluation_at,
        "reason_counts": ordered,
        "latest_by_symbol": latest_by_symbol,
    }


@router.get("/stream")
async def stream_paper(request: Request, db: DbSession) -> StreamingResponse:
    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    account = db.query(PaperAccount).filter(PaperAccount.name == "default").first()
                    if account:
                        portfolio = PaperPortfolio(db, account)
                        open_positions = portfolio.open_positions()
                        unrealized = sum((position.unrealized_pnl for position in open_positions), Decimal("0"))
                        metrics = PaperMetrics(db, account.id).summary()
                        payload = {
                            "account_id": account.id,
                            "status": account.status,
                            "cash_balance": float(account.cash_balance),
                            "equity": float(portfolio.equity()),
                            "realized_pnl": float(account.realized_pnl),
                            "unrealized_pnl": float(unrealized),
                            "exposure": float(portfolio.exposure_pct()),
                            "metrics": metrics,
                        }
                        yield f"data: {json.dumps(payload)}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'status': 'error'})}\n\n"
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _get_or_create_account(db: DbSession, name: str = "default", initial_balance: Decimal = Decimal("10000")) -> PaperAccount:
    account = db.query(PaperAccount).filter(PaperAccount.name == name).first()
    if account is None:
        account = PaperAccount(name=name, cash_balance=initial_balance, initial_balance=initial_balance)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account
