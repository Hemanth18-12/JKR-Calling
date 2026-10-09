import datetime
import time
import uuid
from unittest.mock import AsyncMock, patch
import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.config import Settings
from app.modules.identity.firebase_auth import verify_firebase_id_token
from app.modules.identity import service as identity_service
from jkr_db.models.identity import User, PasswordCredential, Session as SessionModel, OAuthIdentity
from jkr_db.models.tenancy import Organization, Workspace, WorkspaceMember, Role


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            User.metadata.create_all,
            tables=[
                User.__table__,
                PasswordCredential.__table__,
                SessionModel.__table__,
                OAuthIdentity.__table__,
                Organization.__table__,
                Workspace.__table__,
                WorkspaceMember.__table__,
                Role.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        # Seed workspace_owner role
        role = Role(id=uuid.uuid4(), key="workspace_owner", name="Workspace Owner", description="Owner role")
        session.add(role)
        await session.flush()
        yield session
    await engine.dispose()


@pytest.fixture(scope="module")
def rsa_test_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()

    # Generate self-signed x509 cert
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "test.securetoken.google.com"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .sign(private_key, hashes.SHA256(), default_backend())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return {
        "private_key": private_key,
        "cert_pem": cert_pem,
        "kid": "test-google-kid-1",
    }


def make_firebase_token(rsa_test_keys, project_id="test-jkr-project", **payload_overrides):
    now = int(time.time())
    payload = {
        "iss": f"https://securetoken.google.com/{project_id}",
        "aud": project_id,
        "auth_time": now,
        "sub": "firebase-uid-9988",
        "iat": now,
        "exp": now + 3600,
        "email": "google.user@example.com",
        "email_verified": True,
        "name": "Google User",
    }
    payload.update(payload_overrides)

    token = jwt.encode(
        payload,
        rsa_test_keys["private_key"],
        algorithm="RS256",
        headers={"kid": rsa_test_keys["kid"]},
    )
    return token


@pytest.mark.asyncio
async def test_verify_firebase_id_token_success(rsa_test_keys):
    project_id = "test-jkr-project"
    token = make_firebase_token(rsa_test_keys, project_id=project_id)

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ):
        result = await verify_firebase_id_token(token, project_id)
        assert result["email"] == "google.user@example.com"
        assert result["uid"] == "firebase-uid-9988"
        assert result["name"] == "Google User"


@pytest.mark.asyncio
async def test_verify_firebase_id_token_expired(rsa_test_keys):
    project_id = "test-jkr-project"
    now = int(time.time())
    token = make_firebase_token(rsa_test_keys, project_id=project_id, exp=now - 100, iat=now - 200)

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_firebase_id_token(token, project_id)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_firebase_id_token_tampered_signature(rsa_test_keys):
    project_id = "test-jkr-project"
    token = make_firebase_token(rsa_test_keys, project_id=project_id)
    # Tamper with the token signature
    tampered = token[:-6] + "xxxxxx"

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_firebase_id_token(tampered, project_id)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_firebase_id_token_unverified_email(rsa_test_keys):
    project_id = "test-jkr-project"
    token = make_firebase_token(rsa_test_keys, project_id=project_id, email_verified=False)

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ):
        with pytest.raises(HTTPException) as exc_info:
            await verify_firebase_id_token(token, project_id)
        assert exc_info.value.status_code == 403
        assert "verified" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_authenticate_with_google_creates_and_links(memory_db: AsyncSession, rsa_test_keys):
    project_id = "test-jkr-project"
    test_settings = Settings(
        firebase_project_id=project_id,
        app_base_url="http://localhost:3000",
        api_base_url="http://localhost:8000",
    )
    token = make_firebase_token(
        rsa_test_keys,
        project_id=project_id,
        email="new.google.signup@example.com",
        name="New Google Person",
    )

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ), patch(
        "app.modules.tenancy.service.providers_service.seed_default_accounts",
        new=AsyncMock(),
    ), patch(
        "app.modules.tenancy.service.tools_service.seed_default_tool_definitions",
        new=AsyncMock(),
    ):
        # 1. New user signs up with Google
        user1 = await identity_service.authenticate_with_google(
            memory_db,
            id_token=token,
            settings=test_settings,
        )
        assert user1.email == "new.google.signup@example.com"
        assert user1.full_name == "New Google Person"
        assert user1.is_platform_super_admin is False

        # Check workspace membership created
        res = await memory_db.execute(
            select(WorkspaceMember).where(WorkspaceMember.user_id == user1.id)
        )
        membership = res.scalar_one_or_none()
        assert membership is not None

        # Check OAuthIdentity row created with google_sub
        oauth_res = await memory_db.execute(
            select(OAuthIdentity).where(OAuthIdentity.user_id == user1.id)
        )
        oauth_id = oauth_res.scalar_one_or_none()
        assert oauth_id is not None
        assert oauth_id.provider == "google"
        assert oauth_id.provider_user_id == "firebase-uid-9988"
        assert oauth_id.email == "new.google.signup@example.com"

        # 2. Re-login with the same Google token returns identical user account (idempotent / linking)
        user2 = await identity_service.authenticate_with_google(
            memory_db,
            id_token=token,
            settings=test_settings,
        )
        assert user2.id == user1.id
        assert user2.email == user1.email

        # 3. Existing user created previously via OTP/password: logs in via Google without duplicate
        existing_otp_user = User(
            email="existing.otp@example.com",
            full_name="Existing OTP User",
            is_platform_super_admin=False,
        )
        memory_db.add(existing_otp_user)
        await memory_db.flush()

        otp_token = make_firebase_token(
            rsa_test_keys,
            project_id=project_id,
            email="existing.otp@example.com",
            name="Existing OTP User",
            sub="google-sub-otp-user",
        )
        linked_user = await identity_service.authenticate_with_google(
            memory_db,
            id_token=otp_token,
            settings=test_settings,
        )
        assert linked_user.id == existing_otp_user.id
        # Verify OAuthIdentity linked to the existing user
        linked_oauth = (
            await memory_db.execute(
                select(OAuthIdentity).where(OAuthIdentity.user_id == existing_otp_user.id)
            )
        ).scalar_one_or_none()
        assert linked_oauth is not None
        assert linked_oauth.provider_user_id == "google-sub-otp-user"


@pytest.mark.asyncio
async def test_authenticate_with_google_superadmin_gate(memory_db: AsyncSession, rsa_test_keys):
    project_id = "test-jkr-project"
    test_settings = Settings(
        firebase_project_id=project_id,
        app_base_url="http://localhost:3000",
        api_base_url="http://localhost:8000",
    )
    admin_token = make_firebase_token(
        rsa_test_keys,
        project_id=project_id,
        email="jkrcalling4@gmail.com",
        name="JKR Super Admin",
    )

    with patch(
        "app.modules.identity.firebase_auth._get_google_public_certs",
        return_value={rsa_test_keys["kid"]: rsa_test_keys["cert_pem"]},
    ), patch(
        "app.modules.tenancy.service.providers_service.seed_default_accounts",
        new=AsyncMock(),
    ), patch(
        "app.modules.tenancy.service.tools_service.seed_default_tool_definitions",
        new=AsyncMock(),
    ):
        admin_user = await identity_service.authenticate_with_google(
            memory_db,
            id_token=admin_token,
            settings=test_settings,
        )
        assert admin_user.email == "jkrcalling4@gmail.com"
        assert admin_user.is_platform_super_admin is True
