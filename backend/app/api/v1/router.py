from fastapi import APIRouter

from app.api.v1.account import router as account_router
from app.api.v1.auth import router as auth_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.circuit_breaker import router as circuit_breaker_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.market_data import router as market_data_router
from app.api.v1.paper import router as paper_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.regime import router as regime_router
from app.api.v1.health import router as health_router
from app.api.v1.walkforward import router as walkforward_router
from app.api.v1.execution_quality import router as execution_quality_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(backtests_router)
api_router.include_router(dashboard_router)
api_router.include_router(paper_router)
api_router.include_router(portfolio_router)
api_router.include_router(regime_router)
api_router.include_router(health_router)
api_router.include_router(walkforward_router)
api_router.include_router(account_router)
api_router.include_router(reconciliation_router)
api_router.include_router(circuit_breaker_router)
api_router.include_router(market_data_router)
api_router.include_router(execution_quality_router)

