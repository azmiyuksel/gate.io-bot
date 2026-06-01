from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.api.v1.account import router as account_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.circuit_breaker import router as circuit_breaker_router
from app.api.v1.market_data import router as market_data_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.walkforward import router as walkforward_router
from app.api.v1.paper import router as paper_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.regime import router as regime_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.db.init_db import init_db

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(api_router)
app.include_router(backtests_router, prefix="/api")
app.include_router(walkforward_router, prefix="/api")
app.include_router(walkforward_router)
app.include_router(paper_router, prefix="/api")
app.include_router(paper_router)
app.include_router(portfolio_router, prefix="/api")
app.include_router(portfolio_router)
app.include_router(regime_router, prefix="/api")
app.include_router(regime_router)
app.include_router(health_router, prefix="/api")
app.include_router(health_router)
app.include_router(account_router, prefix="/api")
app.include_router(account_router)
app.include_router(reconciliation_router, prefix="/api")
app.include_router(reconciliation_router)
app.include_router(circuit_breaker_router, prefix="/api")
app.include_router(circuit_breaker_router)
app.include_router(market_data_router, prefix="/api")
app.include_router(market_data_router)



