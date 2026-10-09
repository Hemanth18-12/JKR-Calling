from __future__ import annotations

import pytest
from datetime import datetime
from fastapi import HTTPException
from app.config import get_settings
from app.modules.identity import service
from jkr_db.session import get_session
from jkr_db.models.identity import User


@pytest.fixture(autouse=True)
async def cleanup_db():
    yield
    from jkr_db import session
    if session._engine is not None:
        await session._engine.dispose()
        session._engine = None
        session._session_factory = None


@pytest.mark.asyncio
async def test_google_oauth_url_generation():
    """Verify that Google OAuth URL is properly generated with all necessary parameters."""
    settings = get_settings()
    url, enabled = await service.get_google_oauth_url(settings=settings, state="test_state_123")
    assert "https://accounts.google.com/o/oauth2/v2/auth" in url
    assert "response_type=code" in url
    assert "scope=" in url
    assert "state=test_state_123" in url


@pytest.mark.asyncio
async def test_google_oauth_callback_creates_user_and_workspace():
    """Verify that a new user authenticating with Google gets created with a workspace and credentials."""
    settings = get_settings().model_copy(
        update={"google_client_id": "test_google_client_id", "google_client_secret": "test_google_secret"}
    )
    timestamp = int(datetime.now().timestamp())
    test_email = f"google_new_user_{timestamp}@gmail.com"

    import httpx
    from unittest.mock import patch, MagicMock

    async def mock_post(url, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(url):
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {"access_token": "mock_token_abc"}
            return mock_res
        raise ValueError(f"Unexpected post: {url}")

    async def mock_get(url, *args, **kwargs):
        if "googleapis.com/oauth2/v3/userinfo" in str(url):
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "email": test_email,
                "name": "Google User",
                "sub": f"google_sub_{timestamp}",
            }
            return mock_res
        raise ValueError(f"Unexpected get: {url}")

    with patch.object(httpx.AsyncClient, "post", side_effect=mock_post), \
         patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
        async with get_session() as db:
            user = await service.authenticate_with_google(
                db,
                code="real_google_auth_code_123",
                redirect_uri=None,
                settings=settings,
            )
            assert user is not None
            assert user.email == test_email
            assert user.full_name is not None

            # Verify session creation works cleanly for this user
            session_row, raw_token = await service.create_session(
                db,
                user=user,
                settings=settings,
                user_agent="pytest-agent",
                ip_address="127.0.0.1",
            )
            assert session_row is not None
            assert len(raw_token) > 20
            assert session_row.active_workspace_id is not None


@pytest.mark.asyncio
async def test_google_oauth_callback_links_existing_user():
    """Verify that an existing user logging in via Google is reused rather than duplicated."""
    settings = get_settings().model_copy(
        update={"google_client_id": "test_google_client_id", "google_client_secret": "test_google_secret"}
    )
    timestamp = int(datetime.now().timestamp())
    existing_email = f"google_existing_{timestamp}@gmail.com"

    import httpx
    from unittest.mock import patch, MagicMock

    async def mock_post(url, *args, **kwargs):
        if "oauth2.googleapis.com/token" in str(url):
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {"access_token": "mock_token_abc"}
            return mock_res
        raise ValueError(f"Unexpected post: {url}")

    async def mock_get(url, *args, **kwargs):
        if "googleapis.com/oauth2/v3/userinfo" in str(url):
            mock_res = MagicMock()
            mock_res.status_code = 200
            mock_res.json.return_value = {
                "email": existing_email,
                "name": "Original Name",
                "sub": f"google_sub_existing_{timestamp}",
            }
            return mock_res
        raise ValueError(f"Unexpected get: {url}")

    with patch.object(httpx.AsyncClient, "post", side_effect=mock_post), \
         patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
        async with get_session() as db:
            # First sign up or create user
            first_user = await service.create_user_with_hash(
                db,
                email=existing_email,
                full_name="Original Name",
                password_hash="test_hash_pre_existing",
            )
            first_id = first_user.id

            # Authenticate via Google with the same email
            google_user = await service.authenticate_with_google(
                db,
                code="real_google_auth_code_existing",
                redirect_uri=None,
                settings=settings,
            )
            # Must be the exact same user ID
            assert google_user.id == first_id
            assert google_user.email == existing_email
