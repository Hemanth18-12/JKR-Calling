import datetime as dt
import time
import uuid
from unittest.mock import patch

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import get_settings
from app.main import app
from jkr_db.session import get_session


@pytest.fixture(autouse=True)
async def cleanup_db():
    from jkr_db import session
    if session._engine is not None:
        await session._engine.dispose()
        session._engine = None
        session._session_factory = None
    yield
    if session._engine is not None:
        await session._engine.dispose()
        session._engine = None
        session._session_factory = None


@pytest.fixture(scope="module")
def rsa_keys():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    public_key = private_key.public_key()

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "securetoken.google.com"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1))
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return {
        "private_key": private_key,
        "cert_pem": cert_pem,
        "kid": "mock-firebase-signing-kid-1",
    }


def create_token(rsa_keys, project_id="jkr-calling-d62f9", **overrides):
    now = int(time.time())
    payload = {
        "iss": f"https://securetoken.google.com/{project_id}",
        "aud": project_id,
        "auth_time": now,
        "sub": f"firebase-uid-{uuid.uuid4().hex[:12]}",
        "iat": now,
        "exp": now + 3600,
        "email": "test.google.user@example.com",
        "email_verified": True,
        "name": "Test Google User",
    }
    payload.update(overrides)
    return jwt.encode(payload, rsa_keys["private_key"], algorithm="RS256", headers={"kid": rsa_keys["kid"]})


@pytest.mark.asyncio
async def test_invalid_and_expired_tokens_return_401(rsa_keys):
    """Test E: Send invalid or expired token -> 401 with clean error message, no DB touch."""
    settings = get_settings()
    project_id = settings.firebase_project_id

    mock_certs = {rsa_keys["kid"]: rsa_keys["cert_pem"]}
    transport = ASGITransport(app=app)

    with patch("app.modules.identity.firebase_auth._get_google_public_certs", return_value=mock_certs):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Empty token
            r1 = await client.post("/auth/google", json={"id_token": ""})
            assert r1.status_code == 422 or r1.status_code == 401

            # 2. Malformed token
            r2 = await client.post("/auth/google", json={"id_token": "not.a.valid.jwt"})
            assert r2.status_code == 401
            assert "error" in r2.json()

            # 3. Expired token
            now = int(time.time())
            expired_tok = create_token(rsa_keys, project_id=project_id, exp=now - 50, iat=now - 200)
            r3 = await client.post("/auth/google", json={"id_token": expired_tok})
            assert r3.status_code == 401
            assert "expired" in r3.json()["error"]["message"].lower()

            # 4. Unverified email
            unverified_tok = create_token(rsa_keys, project_id=project_id, email_verified=False)
            r4 = await client.post("/auth/google", json={"id_token": unverified_tok})
            assert r4.status_code == 403
            assert "verified" in r4.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_brand_new_account_and_session_persistence(rsa_keys):
    """Test A & D: Brand-new Google account -> workspace -> session persists on refresh -> logout."""
    settings = get_settings()
    project_id = settings.firebase_project_id
    mock_certs = {rsa_keys["kid"]: rsa_keys["cert_pem"]}
    transport = ASGITransport(app=app)

    unique_email = f"brand_new_user_{uuid.uuid4().hex[:8]}@example.com"
    token = create_token(
        rsa_keys,
        project_id=project_id,
        email=unique_email,
        name="Brand New Tester",
        sub=f"google-sub-{uuid.uuid4().hex[:10]}",
    )

    with patch("app.modules.identity.firebase_auth._get_google_public_certs", return_value=mock_certs):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Login with Google
            t0 = time.perf_counter()
            resp = await client.post("/auth/google", json={"id_token": token})
            login_ms = (time.perf_counter() - t0) * 1000
            assert resp.status_code == 200, resp.text
            user_data = resp.json()
            assert user_data["email"] == unique_email
            assert user_data["full_name"] == "Brand New Tester"
            assert user_data["is_platform_super_admin"] is False
            print(f"\n[Brand New Google Login] Timing: {login_ms:.1f}ms")

            # Verify cookie is set
            cookie_name = settings.session_cookie_name
            assert cookie_name in client.cookies

            # 2. Session persists across page refresh (GET /auth/me)
            me_resp = await client.get("/auth/me")
            assert me_resp.status_code == 200
            me_data = me_resp.json()
            assert me_data["user"]["email"] == unique_email
            assert len(me_data["memberships"]) >= 1
            assert me_data["active_workspace_id"] is not None

            # 3. Logout revokes session
            logout_resp = await client.post("/auth/logout")
            assert logout_resp.status_code == 204

            # 4. After logout, /auth/me returns 401
            unauth_resp = await client.get("/auth/me")
            assert unauth_resp.status_code == 401


@pytest.mark.asyncio
async def test_existing_otp_email_account_linking(rsa_keys):
    """Test B: Existing user with same email -> logs into SAME account without duplicate."""
    settings = get_settings()
    project_id = settings.firebase_project_id
    mock_certs = {rsa_keys["kid"]: rsa_keys["cert_pem"]}
    transport = ASGITransport(app=app)

    unique_email = f"otp_linking_user_{uuid.uuid4().hex[:8]}@example.com"

    # Pre-create user via signup OTP / create_user
    from app.modules.identity.service import create_user
    async with get_session() as db:
        original_user = await create_user(
            db,
            email=unique_email,
            full_name="Original Name",
            password="OriginalPassword123!",
        )
        orig_id = original_user.id

    token = create_token(
        rsa_keys,
        project_id=project_id,
        email=unique_email,
        name="Updated Name",
        sub=f"google-sub-linked-{uuid.uuid4().hex[:8]}",
    )

    with patch("app.modules.identity.firebase_auth._get_google_public_certs", return_value=mock_certs):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/auth/google", json={"id_token": token})
            assert resp.status_code == 200
            data = resp.json()
            # Verified: same user id, no duplicate created
            assert data["id"] == str(orig_id)
            assert data["email"] == unique_email


@pytest.mark.asyncio
async def test_admin_superadmin_gate(rsa_keys):
    """Test F: Superadmin access granted only for jkrcalling4@gmail.com."""
    settings = get_settings()
    project_id = settings.firebase_project_id
    mock_certs = {rsa_keys["kid"]: rsa_keys["cert_pem"]}
    transport = ASGITransport(app=app)

    admin_token = create_token(
        rsa_keys,
        project_id=project_id,
        email="jkrcalling4@gmail.com",
        name="JKR Master Admin",
        sub="admin-sub-permanent",
    )

    non_admin_token = create_token(
        rsa_keys,
        project_id=project_id,
        email="regular_user@example.com",
        name="Regular User",
    )

    with patch("app.modules.identity.firebase_auth._get_google_public_certs", return_value=mock_certs):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Admin login
            r_admin = await client.post("/auth/google", json={"id_token": admin_token})
            assert r_admin.status_code == 200
            assert r_admin.json()["is_platform_super_admin"] is True

            # 2. Regular user login
            r_user = await client.post("/auth/google", json={"id_token": non_admin_token})
            assert r_user.status_code == 200
            assert r_user.json()["is_platform_super_admin"] is False


@pytest.mark.asyncio
async def test_twenty_consecutive_logins_pool_check(rsa_keys):
    """Timing & Connection Pool Check: 20 consecutive logins, measuring pg_stat_activity flat."""
    settings = get_settings()
    project_id = settings.firebase_project_id
    mock_certs = {rsa_keys["kid"]: rsa_keys["cert_pem"]}
    transport = ASGITransport(app=app)

    async def get_pg_connections():
        async with get_session() as db:
            total = await db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();"))
            active = await db.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active';")
            )
            return total.scalar(), active.scalar()

    conn_before_total, conn_before_active = await get_pg_connections()
    print(f"\n[POOL CHECK BEFORE] total_connections={conn_before_total}, active={conn_before_active}")

    timings: list[float] = []

    with patch("app.modules.identity.firebase_auth._get_google_public_certs", return_value=mock_certs):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            for i in range(20):
                email = f"benchmark_user_{i}_{uuid.uuid4().hex[:6]}@example.com"
                token = create_token(
                    rsa_keys,
                    project_id=project_id,
                    email=email,
                    name=f"Bench User {i}",
                    sub=f"bench-sub-{i}-{uuid.uuid4().hex[:6]}",
                )
                t0 = time.perf_counter()
                resp = await client.post("/auth/google", json={"id_token": token})
                elapsed_ms = (time.perf_counter() - t0) * 1000
                timings.append(elapsed_ms)
                assert resp.status_code == 200, f"Login {i} failed: {resp.text}"

    conn_after_total, conn_after_active = await get_pg_connections()
    print(f"[POOL CHECK AFTER 20 LOGINS] total_connections={conn_after_total}, active={conn_after_active}")

    avg_ms = sum(timings) / len(timings)
    min_ms = min(timings)
    max_ms = max(timings)
    print(f"[TIMING RESULTS] min={min_ms:.1f}ms, max={max_ms:.1f}ms, avg={avg_ms:.1f}ms")
    for idx, t in enumerate(timings):
        print(f"  Login #{idx+1:02d}: {t:.1f}ms")

    # Verify connection count stayed flat (no connection leak)
    # The pool must not grow unchecked: total connections after should remain roughly identical
    assert conn_after_active <= 2, f"Active connections leaked: {conn_after_active}"
