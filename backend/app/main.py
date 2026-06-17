import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import require_admin
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
    watchdog_task = None
    try:
        for warning in settings.validate_runtime_secrets():
            logger.warning("config_warning", extra={"warning": warning})
        init_db()
        _initialized = True
    except Exception as exc:
        logger.exception("startup_failed")
        _init_error = str(exc)
    # Start the live-worker watchdog (no-op unless WORKER_WATCHDOG_ENABLED): the
    # API is a separate, always-on process, so it can detect the scheduler dying.
    if _initialized and settings.worker_watchdog_enabled:
        import asyncio

        from app.workers.watchdog import worker_watchdog_loop

        watchdog_task = asyncio.create_task(worker_watchdog_loop())
    try:
        yield
    finally:
        if watchdog_task is not None:
            watchdog_task.cancel()


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
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration = time.perf_counter() - start
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
        correlation_id.reset(token)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log unhandled errors with the correlation id and return a safe payload."""
    request_id = correlation_id.get() or request.headers.get("X-Request-ID") or str(uuid.uuid4())
    logger.exception("unhandled_exception", extra={"path": request.url.path, "request_id": request_id})
    detail = "Internal server error"
    if not settings.is_production:
        detail = f"{type(exc).__name__}: {exc}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.get("/health")
def health() -> dict:
    """Liveness probe: process is up."""
    status = "ok"
    detail = None
    if _init_error:
        status = "degraded"
        detail = _init_error
    elif not _initialized:
        status = "starting"
    return {"status": status, "detail": detail}


@app.get("/health/worker")
def worker_health() -> dict:
    """Live-worker liveness: heartbeat age and staleness for external monitors."""
    from app.db.session import SessionLocal
    from app.workers.heartbeat import heartbeat_age_seconds, is_stale

    db = SessionLocal()
    try:
        age = heartbeat_age_seconds(db, "scheduler")
    finally:
        db.close()
    threshold = settings.worker_heartbeat_stale_seconds
    return {
        "worker": "scheduler",
        "age_seconds": age,
        "stale": is_stale(age, threshold),
        "threshold_seconds": threshold,
        "watchdog_enabled": settings.worker_watchdog_enabled,
    }


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


@app.get("/debug/config", dependencies=[Depends(require_admin)])
def debug_config() -> dict:
    """Return initialization status for debugging deployments."""
    return {
        "initialized": _initialized,
        "init_error": _init_error,
        "environment": settings.environment,
        "database_url_redacted": settings.database_url.split("@")[-1] if "@" in settings.database_url else "unknown",
        "secret_key_set": settings.secret_key not in ("", "change-me"),
        "fernet_key_set": bool(settings.fernet_key),
    }


# All application endpoints are served under a single /api/v1 prefix.
app.include_router(api_router)
