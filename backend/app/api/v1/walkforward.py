from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.deps import DbSession, current_user_role, require_admin
from app.backtest.engine import HistoricalDataLoader
from app.models.entities import WalkForwardRun, WalkForwardWindow
from app.models.enums import WalkForwardMode, WalkForwardStatus
from app.schemas.walkforward import WalkForwardDetail, WalkForwardListItem, WalkForwardStart
from app.services.exchange.gateio import GateIOClient
from app.walkforward.engine import WalkForwardEngine
from app.walkforward.models import SplitMode, WalkForwardConfig
from app.walkforward.report import pdf_report_placeholder

router = APIRouter(prefix="/walkforward", tags=["walkforward"], dependencies=[Depends(current_user_role)])


@router.post("/start", dependencies=[Depends(require_admin)])
async def start_walkforward(payload: WalkForwardStart, db: DbSession) -> dict:
    run = WalkForwardRun(
        strategy_name=payload.strategy_name,
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        mode=WalkForwardMode(payload.mode),
        start_at=payload.start_at,
        end_at=payload.end_at,
        train_period_days=payload.train_period_days,
        test_period_days=payload.test_period_days,
        step_days=payload.step_days,
        n_trials=payload.n_trials,
        initial_cash=payload.initial_cash,
        status=WalkForwardStatus.running,
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
            data = loader.load_from_csv(payload.csv_data, payload.timeframe)
            loader.cache(data, payload.symbol, payload.timeframe, "csv")
        elif payload.data_source == "gateio":
            data = await loader.load_from_gateio(
                payload.symbol, payload.timeframe, payload.start_at, payload.end_at
            )
        else:
            data = loader.load_from_cache(payload.symbol, payload.timeframe, payload.start_at, payload.end_at)

        result = WalkForwardEngine().run(data, _config_from_payload(payload))
        _persist_result(db, run, result)
        return {
            "id": run.id,
            "status": run.status,
            "aggregated_metrics": run.aggregated_metrics,
            "deployment_decision": run.deployment_decision,
        }
    except HTTPException:
        run.status = WalkForwardStatus.failed
        run.error = "Invalid walk-forward request"
        db.commit()
        raise
    except Exception as exc:
        run.status = WalkForwardStatus.failed
        run.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if client:
            await client.close()


@router.get("", response_model=list[WalkForwardListItem])
def list_walkforward(db: DbSession) -> list[WalkForwardListItem]:
    runs = db.query(WalkForwardRun).order_by(WalkForwardRun.created_at.desc()).limit(100).all()
    return [
        WalkForwardListItem(
            id=run.id,
            created_at=run.created_at,
            strategy_name=run.strategy_name,
            symbol=run.symbol,
            timeframe=run.timeframe,
            mode=run.mode,
            status=run.status,
            robustness_score=float((run.aggregated_metrics or {}).get("robustness_score", 0)),
            wfe=float((run.aggregated_metrics or {}).get("wfe", 0)),
            consistency_score=float((run.aggregated_metrics or {}).get("consistency_score", 0)),
            average_sharpe=float((run.aggregated_metrics or {}).get("average_sharpe", 0)),
            average_drawdown=float((run.aggregated_metrics or {}).get("average_drawdown", 0)),
            deployment_decision=(run.deployment_decision or {}).get("decision", "AUTO_DEPLOYMENT_REJECT"),
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=WalkForwardDetail)
def get_walkforward(run_id: int, db: DbSession) -> WalkForwardDetail:
    run = _get_run(db, run_id)
    return WalkForwardDetail(
        id=run.id,
        strategy_name=run.strategy_name,
        symbol=run.symbol,
        timeframe=run.timeframe,
        mode=run.mode,
        status=run.status,
        parameters=run.parameters or {},
        aggregated_metrics=run.aggregated_metrics or {},
        combined_equity_curve=run.combined_equity_curve or [],
        monte_carlo_results=run.monte_carlo_results or {},
        deployment_decision=run.deployment_decision or {},
        overfit_warnings=run.overfit_warnings or [],
        report=run.report or {},
        windows=[
            {
                "id": window.id,
                "window_id": window.window_id,
                "train_start": window.train_start.isoformat(),
                "train_end": window.train_end.isoformat(),
                "test_start": window.test_start.isoformat(),
                "test_end": window.test_end.isoformat(),
                "best_params": window.best_params,
                "train_metrics": window.train_metrics,
                "test_metrics": window.test_metrics,
                "equity_curve": window.equity_curve,
                "trades": window.trades,
                "wfe": float(window.wfe),
                "overfit_warning": window.overfit_warning,
            }
            for window in sorted(run.windows, key=lambda item: item.window_id)
        ],
    )


@router.get("/{run_id}/report")
def get_report(run_id: int, db: DbSession) -> Response:
    run = _get_run(db, run_id)
    return Response(
        content=pdf_report_placeholder(run.id, run.aggregated_metrics or {}),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="walkforward-{run.id}.pdf"'},
    )


@router.delete("/{run_id}", dependencies=[Depends(require_admin)])
def delete_walkforward(run_id: int, db: DbSession) -> dict:
    run = _get_run(db, run_id)
    db.delete(run)
    db.commit()
    return {"status": "deleted"}


def _get_run(db: DbSession, run_id: int) -> WalkForwardRun:
    run = db.get(WalkForwardRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Walk-forward run not found")
    return run


def _config_from_payload(payload: WalkForwardStart) -> WalkForwardConfig:
    return WalkForwardConfig(
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        start_at=payload.start_at,
        end_at=payload.end_at,
        mode=SplitMode(payload.mode),
        train_period_days=payload.train_period_days,
        test_period_days=payload.test_period_days,
        step_days=payload.step_days,
        n_trials=payload.n_trials,
        initial_cash=float(payload.initial_cash),
        base_parameters=payload.parameters,
    )


def _persist_result(db: DbSession, run: WalkForwardRun, result: dict) -> None:
    run.status = WalkForwardStatus.completed
    run.aggregated_metrics = result["aggregated_metrics"]
    run.combined_equity_curve = result["combined_equity_curve"]
    run.monte_carlo_results = result["monte_carlo_results"]
    run.deployment_decision = result["deployment_decision"]
    if not result["deployment_decision"].get("approved"):
        run.status = WalkForwardStatus.rejected
    run.overfit_warnings = result["overfit_warnings"]
    run.report = result["report"]
    run.completed_at = datetime.now(UTC)
    for window in result["windows"]:
        db.add(
            WalkForwardWindow(
                run_id=run.id,
                window_id=window.window_id,
                train_start=window.train_start,
                train_end=window.train_end,
                test_start=window.test_start,
                test_end=window.test_end,
                best_params=window.best_params,
                train_metrics=window.train_metrics,
                test_metrics=window.test_metrics,
                equity_curve=window.equity_curve,
                trades=window.trades,
                wfe=Decimal(str(window.wfe)),
                overfit_warning=window.overfit_warning,
            )
        )
    db.commit()
    db.refresh(run)
