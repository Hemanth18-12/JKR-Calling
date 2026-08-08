from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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
from app.modules.operations.router import router as operations_router
from app.modules.providers.router import router as providers_router
from app.modules.tenancy.router import router as tenancy_router
from app.modules.tools.router import router as tools_router

settings = get_settings()

app = FastAPI(title="JKR AI Calling API", version="0.1.0", root_path="")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_base_url],
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
    return {"status": "ok", "env": settings.app_env}


for r in (
    identity_router, tenancy_router, providers_router, agents_router, calls_router, knowledge_router,
    contacts_router, campaigns_router, tools_router, operations_router, analytics_router, experiments_router,
    compliance_router, billing_router, integrations_router, live_call_router,
):
    app.include_router(r, prefix="/api/v1")
