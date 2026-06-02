from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health() -> dict:
    """Liveness probe: process is up. Always cheap, no external dependencies."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict:
    """Readiness probe: verifies the database is reachable."""
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - surface any connectivity failure
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc
    return {"status": "ready"}


# All application endpoints are served under a single /api/v1 prefix.
app.include_router(api_router)
