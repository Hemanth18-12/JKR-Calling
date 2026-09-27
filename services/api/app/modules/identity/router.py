from __future__ import annotations

import logging
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import platform_db
from app.deps import AuthContext, get_auth_context, user_db
from app.modules.identity import service
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    OtpRequiredResponse,
    OtpResentResponse,
    ResendOtpRequest,
    SignupRequest,
    UserOut,
    VerifyOtpRequest,
)
from app.rate_limit import rate_limit
from app.security import hash_password
from jkr_db.models.identity import User
from sqlalchemy import select

logger = logging.getLogger("jkr_api.identity.router")

router = APIRouter(prefix="/auth", tags=["auth"])

# Generous enough that a legitimate user retrying a typo'd password a few
# times never gets blocked, tight enough to blunt a credential-stuffing
# script hitting one IP — see docs/SECURITY_AND_COMPLIANCE.md §7.
_auth_rate_limit = rate_limit("auth", max_requests=20, window_seconds=60)


def _set_session_cookie(response: Response, *, raw_token: str, settings: Settings) -> None:
    samesite = "none" if not settings.is_local else "lax"
    secure = True if samesite == "none" else not settings.is_local
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite=samesite,
        path="/",
    )


@router.post("/signup", response_model=OtpRequiredResponse | UserOut, dependencies=[Depends(_auth_rate_limit)])
async def signup(
    payload: SignupRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> OtpRequiredResponse | UserOut:
    try:
        # Check if email is already registered
        existing = await db.execute(select(User).where(User.email == payload.email.lower()))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

        # Hash password in advance so plaintext is never held in DB
        hashed = hash_password(payload.password)

        await service.issue_verification_otp(
            db,
            email=payload.email,
            purpose="signup",
            settings=settings,
            metadata={"full_name": payload.full_name, "password_hash": hashed},
        )
        return OtpRequiredResponse(
            status="otp_required",
            email=payload.email,
            purpose="signup",
            message="A 6-digit verification code has been sent to your email. Please enter it to complete signup.",
        )
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, TimeoutError, asyncpg.PostgresError) as exc:
        logger.error(
            "[AUTH SIGNUP DB ERROR] Database failure during signup for %s: %s",
            payload.email,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service temporarily unavailable — database connection issue",
        ) from exc


@router.post("/login", response_model=OtpRequiredResponse | UserOut, dependencies=[Depends(_auth_rate_limit)])
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> OtpRequiredResponse | UserOut:
    try:
        user = await service.authenticate_user(db, email=payload.email, password=payload.password)

        await service.issue_verification_otp(
            db,
            email=payload.email,
            purpose="login",
            settings=settings,
            metadata={"user_id": str(user.id)},
        )
        return OtpRequiredResponse(
            status="otp_required",
            email=payload.email,
            purpose="login",
            message="A 6-digit verification code has been sent to your email.",
        )
    except HTTPException:
        raise
    except (SQLAlchemyError, OSError, TimeoutError, asyncpg.PostgresError) as exc:
        logger.error(
            "[AUTH LOGIN DB ERROR] Database connection failure during login for %s: %s",
            payload.email,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="service temporarily unavailable — database connection issue",
        ) from exc


@router.post("/verify-otp", response_model=UserOut, dependencies=[Depends(_auth_rate_limit)])
async def verify_otp(
    payload: VerifyOtpRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    try:
        record = await service.verify_otp_code(
            db,
            email=payload.email,
            purpose=payload.purpose,
            code=payload.code,
            settings=settings,
        )

        if payload.purpose == "signup":
            import json
            meta = json.loads(record.metadata_json or "{}")
            full_name = meta.get("full_name") or "User"
            password_hash = meta.get("password_hash")
            if not password_hash:
                from app.security import hash_password
                password_hash = hash_password("Password1234!")
            user = await service.create_user_with_hash(
                db,
                email=payload.email,
                full_name=full_name,
                password_hash=password_hash,
            )
        else:
            # Login
            result = await db.execute(select(User).where(User.email == payload.email.lower()))
            user = result.scalar_one_or_none()
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User account not found")

        _session, raw_token = await service.create_session(
            db,
            user=user,
            settings=settings,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
        )
        _set_session_cookie(response, raw_token=raw_token, settings=settings)
        return UserOut.model_validate(user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[VERIFY OTP ERROR] Unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Verification failed. Please try again.") from exc


@router.post("/resend-otp", response_model=OtpResentResponse, dependencies=[Depends(_auth_rate_limit)])
async def resend_otp(
    payload: ResendOtpRequest,
    db: AsyncSession = Depends(platform_db),
    settings: Settings = Depends(get_settings),
) -> OtpResentResponse:
    import json
    from jkr_db.models.identity import EmailVerificationCode

    # Lookup previous unconsumed verification code for metadata
    prev_result = await db.execute(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == payload.email.lower(),
            EmailVerificationCode.purpose == payload.purpose,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    prev = prev_result.scalar_one_or_none()
    meta = json.loads(prev.metadata_json) if prev and prev.metadata_json else None

    if payload.purpose == "signup" and not meta:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Signup session not found. Please sign up again.")

    await service.issue_verification_otp(
        db,
        email=payload.email,
        purpose=payload.purpose,
        settings=settings,
        metadata=meta,
    )
    return OtpResentResponse(
        status="otp_sent",
        email=payload.email,
        message="A new 6-digit verification code has been sent.",
    )



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
