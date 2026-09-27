from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import LoginRequest, SignupRequest, _validate_and_normalize_email


@pytest.fixture(autouse=True)
async def cleanup_db():
    yield
    from jkr_db import session
    if session._engine is not None:
        await session._engine.dispose()
        session._engine = None
        session._session_factory = None



def test_invalid_syntax_rejected():
    """Emails with invalid syntax like asdf@asdf must fail immediately."""
    invalid_syntax_emails = [
        "asdf@asdf",
        "user@",
        "@domain.com",
        "plainaddress",
        "user@domain..com",
    ]
    for email in invalid_syntax_emails:
        with pytest.raises((ValidationError, ValueError)) as excinfo:
            SignupRequest(email=email, full_name="Test User", password="Password123!")
        assert "Invalid email syntax" in str(excinfo.value) or "at-sign" in str(excinfo.value)

        with pytest.raises((ValidationError, ValueError)) as excinfo:
            LoginRequest(email=email, password="Password123!")
        assert "Invalid email syntax" in str(excinfo.value) or "at-sign" in str(excinfo.value)


def test_fake_domains_with_no_mx_rejected():
    """Emails with syntactically valid but non-existent or no-MX domains must be rejected."""
    fake_domains = [
        "test@fakefakefake999.com",
        "anything@notarealdomain12345.com",
        "fake@nonexistentdomainabcxyz9999.org",
    ]
    for email in fake_domains:
        with pytest.raises((ValidationError, ValueError)) as excinfo:
            SignupRequest(email=email, full_name="Test User", password="Password123!")
        assert "Domain does not exist or has no valid MX records" in str(excinfo.value)

        with pytest.raises((ValidationError, ValueError)) as excinfo:
            LoginRequest(email=email, password="Password123!")
        assert "Domain does not exist or has no valid MX records" in str(excinfo.value)


def test_real_valid_domains_accepted():
    """Emails with real, active domains and valid MX records must be accepted and normalized."""
    real_emails = [
        ("realtest.jkr.calling@outlook.com", "realtest.jkr.calling@outlook.com"),
        ("test@gmail.com", "test@gmail.com"),
    ]
    for raw, expected in real_emails:
        req = SignupRequest(email=raw, full_name="Real User", password="Password123!")
        assert req.email == expected

        login_req = LoginRequest(email=raw, password="Password123!")
        assert login_req.email == expected


def test_demo_fixture_domains_accepted():
    """.demo domains are explicitly permitted for local seeded fixtures without DNS lookups."""
    fixture_email = "owner@aahadentalcare.demo"
    req = SignupRequest(email=fixture_email, full_name="Demo Owner", password="Password123!")
    assert req.email == fixture_email

    login_req = LoginRequest(email=fixture_email, password="Password123!")
    assert login_req.email == fixture_email


@pytest.mark.asyncio
async def test_otp_issue_and_verify_lifecycle():
    """Verify that OTP codes are generated, securely hashed, verified, and cannot be reused."""
    from datetime import UTC, datetime, timedelta
    from fastapi import HTTPException
    from app.config import get_settings
    from app.modules.identity import service
    from jkr_db.session import get_session

    settings = get_settings()
    test_email = f"pytest_otp_{int(datetime.now().timestamp())}@gmail.com"

    async with get_session() as db:
        # 1. Issue OTP
        rec, code = await service.issue_verification_otp(
            db, email=test_email, purpose="signup", settings=settings,
            metadata={"full_name": "Test Lifecycle", "password_hash": "testhash"},
            force=True
        )
        assert len(code) == 6
        assert code.isdigit()
        assert rec.code_hash != code  # Ensure never stored as plaintext
        assert rec.consumed_at is None

        # 2. Reject wrong code
        with pytest.raises(HTTPException) as exc_info:
            await service.verify_otp_code(db, email=test_email, purpose="signup", code="000000", settings=settings)
        assert exc_info.value.status_code == 400
        assert "Invalid verification code" in exc_info.value.detail

        # 3. Accept correct code
        verified = await service.verify_otp_code(db, email=test_email, purpose="signup", code=code, settings=settings)
        assert verified.consumed_at is not None

        # 4. Reject reuse
        with pytest.raises(HTTPException) as exc_info:
            await service.verify_otp_code(db, email=test_email, purpose="signup", code=code, settings=settings)
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_otp_rate_limiting_and_lockout():
    """Verify that OTP requests enforce a 60-second cooldown and lock out after 5 bad attempts."""
    from datetime import datetime
    from fastapi import HTTPException
    from app.config import get_settings
    from app.modules.identity import service
    from jkr_db.session import get_session

    settings = get_settings()
    test_email = f"cooldown_test_{int(datetime.now().timestamp())}@gmail.com"

    async with get_session() as db:
        # Issue first code
        _rec1, _code1 = await service.issue_verification_otp(
            db, email=test_email, purpose="login", settings=settings, force=False
        )

        # Immediate second code request without force must raise 429
        with pytest.raises(HTTPException) as exc_info:
            await service.issue_verification_otp(
                db, email=test_email, purpose="login", settings=settings, force=False
            )
        assert exc_info.value.status_code == 429
        assert "wait at least 60 seconds" in exc_info.value.detail

        # Issue code with force=True for lockout test
        _rec2, code2 = await service.issue_verification_otp(
            db, email=test_email, purpose="login", settings=settings, force=True
        )

        # Enter wrong code 4 times (must decrement attempts)
        for i in range(1, 5):
            with pytest.raises(HTTPException) as exc_info:
                await service.verify_otp_code(db, email=test_email, purpose="login", code="111111", settings=settings)
            assert exc_info.value.status_code == 400
            assert f"{5 - i} attempt" in exc_info.value.detail

        # 5th wrong attempt must trigger 429 lockout
        with pytest.raises(HTTPException) as exc_info:
            await service.verify_otp_code(db, email=test_email, purpose="login", code="111111", settings=settings)
        assert exc_info.value.status_code == 429
        assert "Too many incorrect attempts" in exc_info.value.detail




