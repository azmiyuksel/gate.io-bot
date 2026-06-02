from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import DbSession, current_user_role, require_admin
from app.backtest.engine import BacktestEngine, HistoricalDataLoader
from app.backtest.models import BacktestConfig
from app.backtest.optimizer import ParameterOptimizer
from app.backtest.reports import pdf_report_placeholder
from app.models.entities import BacktestRun, BacktestTrade
from app.models.enums import BacktestStatus
from app.schemas.backtest import (
    BacktestCreate,
    BacktestDetail,
    BacktestListItem,
    OptimizationRequest,
    WalkForwardRequest,
)
from app.core.config import get_settings
from app.services.exchange.gateio import GateIOClient


def _check_csv_size(csv_data: str) -> None:
    limit = get_settings().max_csv_upload_bytes
    if len(csv_data.encode("utf-8")) > limit:
        raise HTTPException(
            status_code=413, detail=f"csv_data exceeds the {limit // (1024 * 1024)} MB limit"
        )


router = APIRouter(prefix="/backtests", tags=["backtests"], dependencies=[Depends(current_user_role)])


@router.post("", dependencies=[Depends(require_admin)])
async def create_backtest(payload: BacktestCreate, db: DbSession) -> dict:
    run = BacktestRun(
        strategy_name=payload.strategy_name,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        start_at=payload.start_at,
        end_at=payload.end_at,
        initial_cash=payload.initial_cash,
        status=BacktestStatus.running,
        parameters=payload.parameters,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    client = GateIOClient() if payload.data_source == "gateio" else None
    try:
        loader = HistoricalDataLoader(db, client)
        if payload.data_source == "csv":
            if not payload.csv_data:
                raise HTTPException(status_code=400, detail="csv_data is required")
            _check_csv_size(payload.csv_data)
            data = loader.load_from_csv(payload.csv_data, payload.timeframe)
            loader.cache(data, payload.symbol, payload.timeframe, "csv")
        elif payload.data_source == "gateio":
            data = await loader.load_from_gateio(
                payload.symbol, payload.timeframe, payload.start_at, payload.end_at
            )
        else:
            data = loader.load_from_cache(payload.symbol, payload.timeframe, payload.start_at, payload.end_at)

        config = _config_from_run(run)
        result = BacktestEngine().run(data, config)
        _persist_result(db, run, result)
        return {"id": run.id, "status": run.status, "metrics": run.metrics}
    except HTTPException:
        run.status = BacktestStatus.failed
        run.error = "Invalid request"
        db.commit()
        raise
    except Exception as exc:
        run.status = BacktestStatus.failed
        run.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if client:
            await client.close()


@router.get("", response_model=list[BacktestListItem])
def list_backtests(db: DbSession) -> list[BacktestListItem]:
    runs = db.query(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(100).all()
    return [
        BacktestListItem(
            id=run.id,
            created_at=run.created_at,
            strategy_name=run.strategy_name,
            symbol=run.symbol,
            timeframe=run.timeframe,
            status=run.status,
            net_profit=float(run.metrics.get("net_profit", 0) if run.metrics else 0),
            sharpe_ratio=float(run.metrics.get("sharpe_ratio", 0) if run.metrics else 0),
            max_drawdown=float(run.metrics.get("max_drawdown", 0) if run.metrics else 0),
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=BacktestDetail)
def get_backtest(run_id: int, db: DbSession) -> BacktestDetail:
    run = _get_run(db, run_id)
    return BacktestDetail(
        id=run.id,
        strategy_name=run.strategy_name,
        symbol=run.symbol,
        timeframe=run.timeframe,
        status=run.status,
        parameters=run.parameters or {},
        metrics=run.metrics or {},
        charts=run.charts or {},
        optimization_results=run.optimization_results or [],
        walk_forward_results=run.walk_forward_results or [],
        monte_carlo_results=run.monte_carlo_results or {},
        trades=[
            {
                "id": trade.id,
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                "entry_price": float(trade.entry_price),
                "exit_price": float(trade.exit_price or 0),
                "quantity": float(trade.quantity),
                "pnl": float(trade.pnl),
                "pnl_pct": float(trade.pnl_pct),
                "exit_reason": trade.exit_reason,
            }
            for trade in run.trades
        ],
    )


@router.delete("/{run_id}", dependencies=[Depends(require_admin)])
def delete_backtest(run_id: int, db: DbSession) -> dict:
    run = _get_run(db, run_id)
    db.delete(run)
    db.commit()
    return {"status": "deleted"}


@router.post("/{run_id}/optimize", dependencies=[Depends(require_admin)])
def optimize_backtest(run_id: int, payload: OptimizationRequest, db: DbSession) -> dict:
    run = _get_run(db, run_id)
    data = HistoricalDataLoader(db).load_from_cache(run.symbol, run.timeframe, run.start_at, run.end_at)
    results = ParameterOptimizer().grid_search(data, _config_from_run(run), payload.grid)
    run.optimization_results = results
    db.commit()
    return {"status": "completed", "results": results}


@router.post("/{run_id}/walk-forward", dependencies=[Depends(require_admin)])
def walk_forward(run_id: int, payload: WalkForwardRequest, db: DbSession) -> dict:
    run = _get_run(db, run_id)
    data = HistoricalDataLoader(db).load_from_cache(
        run.symbol,
        run.timeframe,
        min(window["train_start"] for window in payload.windows),
        max(window["test_end"] for window in payload.windows),
    )
    results = ParameterOptimizer().walk_forward(data, _config_from_run(run), payload.windows, payload.grid)
    run.walk_forward_results = results
    db.commit()
    return {"status": "completed", "results": results}


@router.get("/{run_id}/report.pdf")
def report_pdf(run_id: int, db: DbSession) -> Response:
    _get_run(db, run_id)
    return Response(
        content=pdf_report_placeholder(run_id),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="backtest-{run_id}.pdf"'},
    )


def _get_run(db: DbSession, run_id: int) -> BacktestRun:
    run = db.get(BacktestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return run


def _config_from_run(run: BacktestRun) -> BacktestConfig:
    params = run.parameters or {}
    return BacktestConfig(
        symbol=run.symbol,
        timeframe=run.timeframe,
        start_at=run.start_at,
        end_at=run.end_at,
        initial_cash=float(run.initial_cash),
        commission_rate=float(params.get("commission_rate", 0.001)),
        maker_fee_rate=float(params.get("maker_fee_rate", 0.0008)),
        execution_mode=str(params.get("execution_mode", "market")),
        limit_offset=float(params.get("limit_offset", 0.0)),
        max_open_positions=int(params.get("max_open_positions", 3)),
        max_capital_per_trade_pct=float(params.get("max_capital_per_trade_pct", 0.01)),
        parameters=params,
    )


def _persist_result(db: DbSession, run: BacktestRun, result: dict) -> None:
    run.status = BacktestStatus.completed
    run.metrics = result["metrics"]
    run.charts = result["charts"]
    run.monte_carlo_results = result["monte_carlo"]
    run.completed_at = datetime.now(UTC)
    for trade in result["trades"]:
        db.add(
            BacktestTrade(
                run_id=run.id,
                symbol=trade.symbol,
                side=trade.side,
                entry_time=trade.entry_time.to_pydatetime(),
                exit_time=trade.exit_time.to_pydatetime(),
                entry_price=Decimal(str(trade.entry_price)),
                exit_price=Decimal(str(trade.exit_price)),
                quantity=Decimal(str(trade.quantity)),
                fee=Decimal(str(trade.fee)),
                pnl=Decimal(str(trade.pnl)),
                pnl_pct=Decimal(str(trade.pnl_pct)),
                exit_reason=trade.exit_reason,
            )
        )
    db.commit()
    db.refresh(run)
