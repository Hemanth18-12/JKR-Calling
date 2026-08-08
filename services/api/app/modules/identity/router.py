from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import platform_db
from app.deps import AuthContext, get_auth_context, user_db
from app.modules.identity import service
from app.modules.identity.schemas import LoginRequest, MeResponse, SignupRequest, UserOut
from app.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# Generous enough that a legitimate user retrying a typo'd password a few
# times never gets blocked, tight enough to blunt a credential-stuffing
# script hitting one IP — see docs/SECURITY_AND_COMPLIANCE.md §7.
_auth_rate_limit = rate_limit("auth", max_requests=20, window_seconds=60)


def _set_session_cookie(response: Response, *, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
        path="/",
    )


@router.post("/signup", response_model=UserOut, status_code=201, dependencies=[Depends(_auth_rate_limit)])
async def signup(
    payload: SignupRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    user = await service.create_user(
        db, email=payload.email, full_name=payload.full_name, password=payload.password
    )
    _session, raw_token = await service.create_session(
        db,
        user=user,
        settings=settings,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookie(response, raw_token=raw_token, settings=settings)
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut, dependencies=[Depends(_auth_rate_limit)])
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    user = await service.authenticate_user(db, email=payload.email, password=payload.password)
    _session, raw_token = await service.create_session(
        db,
        user=user,
        settings=settings,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    _set_session_cookie(response, raw_token=raw_token, settings=settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: AsyncSession = Depends(platform_db),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> None:
    await service.revoke_session(db, token_hash=auth.session.token_hash)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=MeResponse)
async def me(
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    memberships = await service.list_memberships(db, user_id=auth.user.id)
    return MeResponse(
        user=UserOut.model_validate(auth.user),
        memberships=memberships,
        active_workspace_id=auth.session.active_workspace_id,
        google_oauth_enabled=bool(settings.google_client_id and settings.google_client_secret),
    )


class SetActiveWorkspaceRequest(BaseModel):
    workspace_id: uuid.UUID


@router.post("/session/active-workspace", response_model=MeResponse)
async def set_active_workspace(
    payload: SetActiveWorkspaceRequest,
    db: AsyncSession = Depends(user_db),
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_settings),
) -> MeResponse:
    await service.set_active_workspace(
        db, session_row=auth.session, user_id=auth.user.id, workspace_id=payload.workspace_id
    )
    memberships = await service.list_memberships(db, user_id=auth.user.id)
    return MeResponse(
        user=UserOut.model_validate(auth.user),
        memberships=memberships,
        active_workspace_id=auth.session.active_workspace_id,
        google_oauth_enabled=bool(settings.google_client_id and settings.google_client_secret),
    )


@router.post("/oauth/google", status_code=501)
async def oauth_google_stub(settings: Settings = Depends(get_settings)) -> dict:
    # Inert until GOOGLE_CLIENT_ID/SECRET are configured — see
    # docs/DECISIONS/0006-auth.md. Deliberately returns 501, not a redirect,
    # so the frontend can distinguish "not configured" from a real OAuth error.
    return {
        "error": "google_oauth_not_configured",
        "message": "Google login is not configured on this deployment.",
    }
