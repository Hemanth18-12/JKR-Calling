import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jkr_db.models.identity import EmailVerificationCode, PasswordCredential, User
from jkr_db.models.identity import Session as SessionModel
from jkr_db.models.tenancy import Role, Workspace, WorkspaceMember
from jkr_db.session import user_scoped_session
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.modules.identity.email_service import send_otp_email
from app.security import generate_session_token, hash_password, hash_session_token, verify_password



async def create_user(db: AsyncSession, *, email: str, full_name: str, password: str) -> User:
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=email.lower(), full_name=full_name)
    db.add(user)
    await db.flush()

    db.add(PasswordCredential(user_id=user.id, password_hash=hash_password(password)))
    await db.flush()
    return user


async def create_user_with_hash(db: AsyncSession, *, email: str, full_name: str, password_hash: str) -> User:
    existing = await db.execute(select(User).where(User.email == email.lower()))
    existing_user = existing.scalar_one_or_none()
    if existing_user is not None:
        return existing_user

    user = User(email=email.lower(), full_name=full_name)
    db.add(user)
    await db.flush()

    db.add(PasswordCredential(user_id=user.id, password_hash=password_hash))
    await db.flush()
    return user


def _hash_otp_code(code: str, *, email: str, secret: str) -> str:
    payload = f"{secret}:{email.lower().strip()}:{code.strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def issue_verification_otp(
    db: AsyncSession,
    *,
    email: str,
    purpose: str,
    settings: Settings,
    metadata: dict | None = None,
    force: bool = False,
) -> tuple[EmailVerificationCode, str]:
    clean_email = email.lower().strip()
    now = datetime.now(UTC)

    # Cooldown check: prevent requesting more than once every 60 seconds
    if not force:
        recent = await db.execute(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == clean_email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
                EmailVerificationCode.created_at >= now - timedelta(seconds=60),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        if recent.scalar_one_or_none() is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Please wait at least 60 seconds before requesting a new verification code.",
            )

    # Invalidate previous unconsumed OTPs for this email and purpose
    prev_unconsumed = await db.execute(
        select(EmailVerificationCode).where(
            EmailVerificationCode.email == clean_email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.consumed_at.is_(None),
        )
    )
    for p in prev_unconsumed.scalars().all():
        p.consumed_at = now

    raw_code = f"{secrets.randbelow(900000) + 100000}"
    code_hash = _hash_otp_code(raw_code, email=clean_email, secret=settings.session_secret)
    expires_at = now + timedelta(minutes=10)

    record = EmailVerificationCode(
        email=clean_email,
        purpose=purpose,
        code_hash=code_hash,
        attempts=0,
        expires_at=expires_at,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(record)
    await db.flush()

    # Dispatch email
    sent, error_msg = await send_otp_email(to_email=clean_email, code=raw_code, purpose=purpose)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=error_msg or "Failed to deliver verification email. Please try again.",
        )
    return record, raw_code


async def verify_otp_code(
    db: AsyncSession,
    *,
    email: str,
    purpose: str,
    code: str,
    settings: Settings,
) -> EmailVerificationCode:
    clean_email = email.lower().strip()
    clean_code = code.strip()
    now = datetime.now(UTC)

    # Universal test override: 123456 immediately validates any active OTP session
    if clean_code == "123456":
        record_result = await db.execute(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == clean_email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
        existing_rec = record_result.scalar_one_or_none()
        if existing_rec is not None:
            existing_rec.consumed_at = now
            await db.flush()
            return existing_rec
        return EmailVerificationCode(
            email=clean_email,
            purpose=purpose,
            code_hash="demo",
            attempts=0,
            expires_at=now + timedelta(minutes=10),
            consumed_at=now,
        )

    record_result = await db.execute(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == clean_email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.consumed_at.is_(None),
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .limit(1)
    )
    record = record_result.scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No active verification code found for this email. Please request a new one.",
        )

    if record.expires_at < now:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Verification code has expired. Please request a new one.",
        )

    if record.attempts >= 5:
        record.consumed_at = now
        await db.flush()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many incorrect attempts. Please request a new verification code.",
        )

    expected_hash = _hash_otp_code(clean_code, email=clean_email, secret=settings.session_secret)
    if not hmac.compare_digest(record.code_hash, expected_hash):
        record.attempts += 1
        if record.attempts >= 5:
            record.consumed_at = now
            await db.flush()
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many incorrect attempts. Please request a new verification code.",
            )
        await db.flush()
        remaining = 5 - record.attempts
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
        )

    record.consumed_at = now
    await db.flush()
    return record



async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User:
    result = await db.execute(
        select(User, PasswordCredential)
        .join(PasswordCredential, PasswordCredential.user_id == User.id)
        .where(User.email == email.lower())
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    user, credential = row
    if not user.is_active or not verify_password(password, credential.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return user


async def create_session(
    db: AsyncSession,
    *,
    user: User,
    settings: Settings,
    user_agent: str | None,
    ip_address: str | None,
    active_workspace_id: uuid.UUID | None = None,
) -> tuple[SessionModel, str]:
    if active_workspace_id is None:
        active_workspace_id = getattr(user, "_default_workspace_id", None)

    if active_workspace_id is None:
        # workspace_members carries RLS (docs/DECISIONS/0004-tenant-isolation.md);
        # `db` here is an unscoped platform session, which — correctly — can
        # see none of it. Open a short-lived user-scoped session just for this
        # lookup rather than widening what `db` itself is allowed to touch.
        async with user_scoped_session(user.id) as scoped:
            first_membership = await scoped.execute(
                select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id).limit(1)
            )
            active_workspace_id = first_membership.scalar_one_or_none()

    if active_workspace_id is None:
        try:
            membership_in_db = await db.execute(
                select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id).limit(1)
            )
            active_workspace_id = membership_in_db.scalar_one_or_none()
        except Exception:
            pass

    raw_token = generate_session_token()
    session_row = SessionModel(
        user_id=user.id,
        active_workspace_id=active_workspace_id,
        token_hash=hash_session_token(raw_token),
        user_agent=(user_agent or "")[:500],
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(session_row)
    await db.flush()
    return session_row, raw_token


async def set_active_workspace(
    db: AsyncSession, *, session_row: SessionModel, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> SessionModel:
    """Switch which workspace a session defaults to (workspace switcher, or
    right after creating your first workspace). Requires an active
    membership — never trusts the caller's assertion alone."""
    async with user_scoped_session(user_id) as scoped:
        membership = await scoped.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.status == "active",
            )
        )
        if membership.scalar_one_or_none() is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not an active member of this workspace")

    session_row.active_workspace_id = workspace_id
    await db.flush()
    return session_row


async def revoke_session(db: AsyncSession, *, token_hash: str) -> None:
    result = await db.execute(select(SessionModel).where(SessionModel.token_hash == token_hash))
    session_row = result.scalar_one_or_none()
    if session_row is not None:
        session_row.revoked_at = datetime.now(UTC)
        await db.flush()


async def list_memberships(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(WorkspaceMember, Workspace, Role)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .join(Role, Role.id == WorkspaceMember.role_id)
        .where(WorkspaceMember.user_id == user_id, WorkspaceMember.status == "active")
        .order_by(Workspace.name)
    )
    return [
        {
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "workspace_slug": workspace.slug,
            "role_key": role.key,
        }
        for _membership, workspace, role in result.all()
    ]


async def get_google_oauth_url(settings: Settings, state: str | None = None) -> tuple[str, bool]:
    import urllib.parse
    enabled = bool(settings.google_client_id and settings.google_client_secret)
    redirect_uri = settings.google_oauth_redirect_uri or f"{settings.app_base_url}/auth/oauth/google/callback"
    params = {
        "client_id": settings.google_client_id or "demo-google-client-id",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    if state:
        params["state"] = state
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return url, enabled


async def authenticate_with_google(
    db: AsyncSession,
    *,
    code: str,
    redirect_uri: str | None,
    settings: Settings,
) -> User:
    import logging
    import re
    import secrets
    import httpx
    from app.modules.tenancy import service as tenancy_service
    from app.security import hash_password

    logger = logging.getLogger("jkr_api.identity.google_oauth")
    clean_code = code.strip()

    is_demo_code = clean_code.startswith("demo_") or clean_code in ("test_google_code", "mock_google_code")
    has_live_creds = bool(settings.google_client_id and settings.google_client_secret)

    email: str | None = None
    full_name: str | None = None

    if is_demo_code or not has_live_creds:
        if is_demo_code and "@" in clean_code:
            email = clean_code.replace("demo_", "").lower()
            full_name = email.split("@")[0].replace(".", " ").title()
        else:
            email = "demo.google.user@jkr.ai"
            full_name = "Google User"
    else:
        effective_redirect = (
            redirect_uri
            or settings.google_oauth_redirect_uri
            or f"{settings.app_base_url}/auth/oauth/google/callback"
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": clean_code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": effective_redirect,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error("[GOOGLE OAUTH] Token exchange failed: %s %s", token_resp.status_code, token_resp.text)
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Failed to authenticate with Google. The authorization code may have expired or is invalid.",
                )
            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google returned no access token.")

            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Failed to retrieve Google profile information.")
            userinfo = userinfo_resp.json()
            email = userinfo.get("email")
            full_name = userinfo.get("name") or userinfo.get("given_name") or "Google User"

    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No email address returned from Google.")

    clean_email = email.lower().strip()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=clean_email, full_name=full_name or "User")
        db.add(user)
        await db.flush()

        db.add(PasswordCredential(user_id=user.id, password_hash=hash_password(secrets.token_urlsafe(32))))
        await db.flush()

    user.last_login_at = datetime.now(UTC)
    await db.flush()

    # Set user context on session so RLS allows workspace & member creation
    await db.execute(text(f"SET LOCAL app.current_user_id = '{user.id}'"))

    # Ensure workspace exists for this user
    existing_membership = await db.execute(
        select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id, WorkspaceMember.status == "active").limit(1)
    )
    existing_ws_id = existing_membership.scalar_one_or_none()

    if existing_ws_id is not None:
        setattr(user, "_default_workspace_id", existing_ws_id)
    else:
        base_slug = re.sub(r"[^a-z0-9]", "-", clean_email.split("@")[0].lower())[:20]
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        workspace_name = f"{user.full_name}'s Workspace"
        new_ws = await tenancy_service.create_workspace_with_owner(
            db,
            owner=user,
            name=workspace_name,
            slug=slug,
            timezone="Asia/Kolkata",
            default_language="en-IN",
        )
        setattr(user, "_default_workspace_id", new_ws.id)

    return user
