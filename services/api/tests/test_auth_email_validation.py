from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.identity.schemas import LoginRequest, SignupRequest, _validate_and_normalize_email


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
