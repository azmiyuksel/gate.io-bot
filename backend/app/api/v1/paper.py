from datetime import UTC, datetime, timedelta
from decimal import Decimal
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession, current_user_role, require_admin
from app.models.entities import PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade
from app.models.enums import PaperBotStatus, PaperOrderType, PaperPositionSide, PaperTimeInForce
from app.paper_trading.metrics import PaperMetrics
from app.paper_trading.models import MarketData, PaperSide, TradingSignal
from app.paper_trading.portfolio import PaperPortfolio
from app.paper_trading.broker import PaperBroker
from app.paper_trading.risk_simulator import PaperRiskSimulator
from app.schemas.paper import (
    ManualOrderRequest,
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

logger = logging.getLogger(__name__)

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
    db.query(PaperLog).filter(PaperLog.account_id == account.id).delete()
    db.query(PaperOrder).filter(PaperOrder.account_id == account.id).delete()
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
    # Edge needs the individual closed-trade PnLs (buys carry 0), so pull just that
    # column for non-zero rows — not whole ORM objects.
    closed_pnls = [
        float(p)
        for (p,) in db.query(PaperTrade.realized_pnl)
        .filter(PaperTrade.account_id == account.id, PaperTrade.realized_pnl != 0)
        .order_by(PaperTrade.traded_at.asc())
        .all()
    ]
    edge = trade_economics(closed_pnls)

    # Total fees via a SQL SUM rather than summing every trade row in Python.
    total_fees = float(
        db.query(func.coalesce(func.sum(PaperTrade.fee), 0))
        .filter(PaperTrade.account_id == account.id)
        .scalar()
        or 0
    )
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

    # Daily loss from 24h rolling peak (consistent with risk simulator)
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    peak_24h = (
        db.query(func.max(PaperEquityCurve.equity))
        .filter(
            PaperEquityCurve.account_id == account.id,
            PaperEquityCurve.timestamp >= cutoff,
        )
        .scalar()
    )
    if peak_24h is None:
        peak_24h = float(account.initial_balance)
    peak = max(float(peak_24h), float(equity))
    daily_loss = max(peak - float(equity), 0.0) / peak if peak > 0 else 0.0

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


async def _fetch_current_price(symbol: str) -> float:
    from app.services.exchange.gateio import GateIOClient
    client = GateIOClient()
    try:
        ticker = await client.ticker(symbol)
        if ticker and float(ticker.get("last", 0)) > 0:
            return float(ticker["last"])
    except Exception:
        logger.warning("paper manual-order: failed to fetch price for %s", symbol, exc_info=True)
    finally:
        await client.close()
    return 0.0


@router.post("/manual-order", dependencies=[Depends(require_admin)])
async def manual_order(payload: ManualOrderRequest, db: DbSession) -> dict:
    account = _get_or_create_account(db)
    broker = PaperBroker(db, account)
    risk = PaperRiskSimulator(db, account)
    now = datetime.now(UTC)
    price = await _fetch_current_price(payload.symbol)
    if price <= 0:
        return {"error": "could not fetch current market price"}
    data = MarketData(
        symbol=payload.symbol,
        timestamp=now,
        price=price,
        volume=0.0,
    )
    # Risk-bypass fix: manual entries must pass the SAME risk simulator gate the
    # automatic strategy path uses (daily-loss / drawdown / max-open-positions /
    # max-exposure). Reduce-only closes skip the entry gate (they only reduce).
    if not payload.reduce_only:
        signal = TradingSignal(
            symbol=payload.symbol,
            side=PaperSide.buy if payload.side == "buy" else PaperSide.sell,
            strength=1.0,
            strategy="manual",
            timestamp=now,
            metadata={"manual": True},
        )
        approved, reason = risk.approve_signal(signal, data)
        if not approved:
            return {"error": f"risk_rejected: {reason}"}
    order_type_map = {
        "market": PaperOrderType.market,
        "limit": PaperOrderType.limit,
        "stop": PaperOrderType.stop,
        "stop_limit": PaperOrderType.stop_limit,
        "oco": PaperOrderType.oco,
    }
    pside = None
    if payload.position_side:
        pside = PaperPositionSide(payload.position_side)
    order = await broker.submit_order(
        symbol=payload.symbol,
        side=PaperSide.buy if payload.side == "buy" else PaperSide.sell,
        quantity=payload.quantity,
        order_type=order_type_map[payload.order_type],
        price=payload.price,
        stop_price=payload.stop_price,
        take_profit=payload.take_profit,
        time_in_force=PaperTimeInForce(payload.time_in_force) if payload.time_in_force else PaperTimeInForce.gtc,
        post_only=payload.post_only,
        reduce_only=payload.reduce_only,
        position_side=pside,
        signal={"manual": True, "strategy": "manual"},
        data=data,
    )
    return {"order_id": order.id, "status": order.status, "side": payload.side, "symbol": payload.symbol}


@router.post("/close-position/{position_id}", dependencies=[Depends(require_admin)])
async def close_position(position_id: int, db: DbSession) -> dict:
    account = _get_or_create_account(db)
    position = (
        db.query(PaperPosition)
        .filter(PaperPosition.id == position_id, PaperPosition.account_id == account.id, PaperPosition.is_open.is_(True))
        .first()
    )
    if not position:
        return {"error": "position not found or already closed"}
    price = await _fetch_current_price(position.symbol)
    if price <= 0:
        price = float(position.last_price) if position.last_price > 0 else 0.0
    if price <= 0:
        return {"error": "could not determine current market price"}
    broker = PaperBroker(db, account)
    data = MarketData(
        symbol=position.symbol,
        timestamp=datetime.now(UTC),
        price=price,
        volume=0.0,
    )
    await broker.close_position(position, data, "manual_close")
    return {"closed": True, "position_id": position_id}


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(require_admin)])
async def cancel_order(order_id: int, db: DbSession) -> dict:
    """Cancel a resting limit / stop / stop-limit / OCO order. Has no effect on
    filled or already-cancelled orders."""
    account = _get_or_create_account(db)
    order = (
        db.query(PaperOrder)
        .filter(PaperOrder.id == order_id, PaperOrder.account_id == account.id)
        .first()
    )
    if not order:
        return {"error": "order not found"}
    broker = PaperBroker(db, account)
    broker.cancel_order(order)
    return {"cancelled": True, "order_id": order_id, "status": order.status}


@router.get("/exit-stats")
def exit_stats(db: DbSession) -> dict:
    account = _get_or_create_account(db)
    # Aggregate in the database (GROUP BY exit_reason) instead of loading every
    # closed trade and counting in Python.
    rows = (
        db.query(PaperTrade.exit_reason, func.count())
        .filter(PaperTrade.account_id == account.id, PaperTrade.exit_reason.isnot(None))
        .group_by(PaperTrade.exit_reason)
        .all()
    )
    counts: dict[str, int] = {(reason or "unknown"): int(n) for reason, n in rows}
    total_closed = sum(counts.values())
    return {"counts": counts, "total_closed": total_closed}


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
    # Reason/symbol live inside the JSON payload, so the per-reason tally is done
    # in Python — but pull only (created_at, payload), not whole ORM rows, and let
    # the (account_id, event, created_at) index drive the filter/order.
    rows = (
        db.query(PaperLog.created_at, PaperLog.payload)
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
    last_evaluation_at = rows[0][0].isoformat() if rows else None
    for created_at, payload in rows:
        payload = payload or {}
        reason = payload.get("reason") or "unknown"
        symbol = payload.get("symbol")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        total += 1
        if symbol and symbol not in latest_by_symbol:
            latest_by_symbol[symbol] = {
                "reason": reason,
                "at": created_at.isoformat() if created_at else None,
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
        from app.db.session import SessionLocal
        db_error_streak = 0
        while True:
            if await request.is_disconnected():
                break
            local_db = SessionLocal()
            try:
                account = _get_or_create_account(local_db)
                portfolio = PaperPortfolio(local_db, account)
                open_positions = portfolio.open_positions()
                unrealized = sum((position.unrealized_pnl for position in open_positions), Decimal("0"))
                metrics = PaperMetrics(local_db, account.id).summary()
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
                db_error_streak = 0
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as exc:
                db_error_streak += 1
                logger.warning("paper stream: DB error (streak=%d): %s", db_error_streak, exc)
                yield f"data: {json.dumps({'status': 'error'})}\n\n"
                # After 10 consecutive DB failures the database is likely down
                # for an extended period. Stop the loop so the client's SSE
                # connection closes and reconnects (which will retry from the
                # outside) instead of spamming error events indefinitely.
                if db_error_streak >= 10:
                    logger.error("paper stream: too many consecutive DB errors, giving up")
                    break
            finally:
                local_db.close()
            # 5s cadence: the eval loop runs every 30s and equity is sampled every
            # 5 min, so a faster push only adds DB load that competes with the trade
            # worker for connections/locks without surfacing new information.
            await asyncio.sleep(5)
    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _get_or_create_account(db: DbSession, name: str = "default", initial_balance: Decimal = Decimal("10000")) -> PaperAccount:
    """Get the account by name, creating it on first use.

    The SELECT-then-INSERT pattern can race under concurrent first-requests:
    two callers both see `None`, both INSERT, and the second now violates the
    UNIQUE constraint on `name`. We catch that IntegrityError, roll back, and
    re-read — the winner's row is now visible. This makes creation idempotent
    without a heavier upsert.
    """
    account = db.query(PaperAccount).filter(PaperAccount.name == name).first()
    if account is None:
        account = PaperAccount(name=name, cash_balance=initial_balance, initial_balance=initial_balance)
        db.add(account)
        try:
            db.commit()
            db.refresh(account)
        except IntegrityError:
            # Lost the create race: the winner already inserted this name.
            db.rollback()
            account = db.query(PaperAccount).filter(PaperAccount.name == name).first()
            if account is None:  # pragma: no cover - defensive
                raise
    return account
