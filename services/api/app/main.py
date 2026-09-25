import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jkr_db.session import ping_database

from app.audit import audit_log_middleware
from app.config import get_settings
from app.modules.agents.router import router as agents_router
from app.modules.analytics.router import router as analytics_router
from app.modules.billing.router import router as billing_router
from app.modules.calls.router import router as calls_router
from app.modules.campaigns.router import router as campaigns_router
from app.modules.compliance.router import router as compliance_router
from app.modules.contacts.router import router as contacts_router
from app.modules.experiments.router import router as experiments_router
from app.modules.identity.router import router as identity_router
from app.modules.integrations.router import router as integrations_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.live_call.router import router as live_call_router
from app.modules.live_call.transport.event_loop_lag import event_loop_lag_monitor
from app.modules.live_call.transport.twilio_media_stream import router as twilio_media_stream_router
from app.modules.operations.router import router as operations_router
from app.modules.providers.router import router as providers_router
from app.modules.tenancy.router import router as tenancy_router
from app.modules.tools.router import router as tools_router

logger = logging.getLogger("jkr_api.main")
settings = get_settings()


async def _async_startup_db_check() -> None:
    """Probes DB connectivity without blocking uvicorn from opening $PORT."""
    try:
        success, msg = await ping_database(timeout=15.0)
        if success:
            logger.info("[STARTUP] %s", msg)
        else:
            logger.warning("[STARTUP WARNING] API started with degraded database connectivity: %s", msg)
    except Exception as exc:
        logger.error("[STARTUP ERROR] Database ping failed during startup: %s", exc, exc_info=True)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # P7 §49 — process-wide, started once; see transport/event_loop_lag.py.
    event_loop_lag_monitor.start()

    # Startup DB health check — launched as a task so uvicorn binds to $PORT immediately
    asyncio.create_task(_async_startup_db_check())

    yield
    event_loop_lag_monitor.stop()


app = FastAPI(title="JKR AI Calling API", version="0.1.0", root_path="", lifespan=_lifespan)


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": "jkr-api"}

cors_origins = [settings.app_base_url, "http://localhost:3000"]
if settings.cors_allowed_origins:
    cors_origins.extend([o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


app.middleware("http")(audit_log_middleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.status_code, "message": exc.detail, "details": {}}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": 422,
                "message": "Validation failed",
                "details": {"fields": exc.errors()},
            }
        },
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok", "env": settings.app_env,
        "event_loop_lag_ms": event_loop_lag_monitor.current_lag_ms,
        "event_loop_max_lag_ms": event_loop_lag_monitor.max_lag_ms,
    }


for r in (
    identity_router, tenancy_router, providers_router, agents_router, calls_router, knowledge_router,
    contacts_router, campaigns_router, tools_router, operations_router, analytics_router, experiments_router,
    compliance_router, billing_router, integrations_router, live_call_router, twilio_media_stream_router,
):
    app.include_router(r, prefix="/api/v1")
