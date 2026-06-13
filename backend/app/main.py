import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, correlation_id, get_logger
from app.core.metrics import record_request, render_latest
from app.db.init_db import init_db

settings = get_settings()
logger = get_logger("app.request")

_initialized = False
_init_error: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _initialized, _init_error
    configure_logging()
    for warning in settings.validate_runtime_secrets():
        logger.warning("config_warning", extra={"warning": warning})
    try:
        init_db()
        _initialized = True
    except Exception as exc:
        logger.exception("database_init_failed")
        _init_error = f"Database init failed: {exc}"
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Assign a correlation id, time the request, log it and record metrics."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = correlation_id.set(request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start
        # Use the matched route template to keep metric cardinality bounded.
        # Unmatched paths (404s) collapse to a single label to avoid explosion.
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "unmatched"
        record_request(request.method, route_path, status_code, duration)
        logger.info(
            "request",
            extra={
                "http_method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        # Surface the id to clients and reset the contextvar.
        if "response" in locals():
            response.headers["X-Request-ID"] = request_id
        correlation_id.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unhandled errors with the correlation id and return a safe payload.

    Avoids leaking internal exception detail to clients while keeping the
    request id so the matching server-side log can be found.
    """
    request_id = correlation_id.get()
    logger.exception("unhandled_exception", extra={"path": request.url.path})
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id} if request_id else None,
    )


@app.get("/health")
def health() -> dict:
    """Liveness probe: process is up. Always cheap, no external dependencies."""
    if _init_error:
        return {"status": "degraded", "detail": _init_error}
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


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus scrape endpoint."""
    payload, content_type = render_latest()
    return Response(content=payload, media_type=content_type)


# All application endpoints are served under a single /api/v1 prefix.
app.include_router(api_router)
