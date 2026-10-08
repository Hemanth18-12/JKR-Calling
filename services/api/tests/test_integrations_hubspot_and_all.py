"""Tests for Phase 2: Integrations (Honest states, 404 fix, test runner, HubSpot sync, and all 7 integrations).
Ensures zero fake passes, no broken 404 links, and verified behavior.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.config import get_settings
from app.modules.integrations import service
from app.modules.integrations.schemas import CrmVerifyRequest
from jkr_db.enums import IntegrationStatus, IntegrationType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from jkr_db.models.tenancy import Workspace
from jkr_db.models.integrations import Integration, IntegrationCredential, WebhookEndpoint, WebhookDelivery
from jkr_db.models.contacts import Contact
from jkr_db.models.tools import Appointment

# SQLite list serializer for PostgreSQL ARRAY column
sqlite3.register_adapter(list, json.dumps)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Workspace.metadata.create_all,
            tables=[
                Workspace.__table__,
                Integration.__table__,
                IntegrationCredential.__table__,
                WebhookEndpoint.__table__,
                WebhookDelivery.__table__,
                Contact.__table__,
                Appointment.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def test_workspace(memory_db: AsyncSession) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Test Integrations Workspace",
        slug=f"test-ws-{uuid.uuid4().hex[:8]}",
    )
    memory_db.add(ws)
    await memory_db.flush()
    return ws


@pytest.mark.asyncio
async def test_catalog_honest_states_and_no_404_urls(memory_db: AsyncSession, test_workspace: Workspace):
    """Test 1: Verify catalog returns honest status and no raw webhook 404 URLs in external_url."""
    cat = await service.catalog(memory_db, workspace_id=test_workspace.id)
    assert len(cat) == 7

    cat_map = {item["type"]: item for item in cat}

    # Built-in integrations should be ready/connected with valid internal links
    assert cat_map["google_calendar"]["status"] == "connected"
    assert cat_map["google_calendar"]["external_url"] == "/app/appointments"
    assert cat_map["google_sheets"]["status"] == "connected"
    assert cat_map["google_sheets"]["external_url"] == "/app/appointments"

    # Outgoing webhooks should be not_connected with None external_url (no 404 GET)
    assert cat_map["webhook"]["status"] == "not_connected"
    assert cat_map["webhook"]["external_url"] is None

    # CRM should be not_connected initially
    assert cat_map["crm"]["status"] == "not_connected"
    assert cat_map["crm"]["external_url"] is None

    # Meta, WhatsApp, n8n should be not_connected initially
    assert cat_map["meta_lead_ads"]["status"] == "not_connected"
    assert cat_map["whatsapp"]["status"] == "not_connected"
    assert cat_map["n8n"]["status"] == "not_connected"


@pytest.mark.asyncio
async def test_outgoing_webhook_test_delivery(memory_db: AsyncSession, test_workspace: Workspace):
    """Test 2: Verify outgoing webhook dispatches HMAC-signed payload and records delivery."""
    settings = get_settings()

    # Create active endpoint
    ep = await service.create_webhook_endpoint(
        memory_db,
        workspace_id=test_workspace.id,
        settings=settings,
        url="https://example.com/webhook/test",
        secret="supersecretphrase123",
        event_types=["call.completed"],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"status": "ok"})

        res = await service.run_integration_test(
            memory_db,
            workspace_id=test_workspace.id,
            integration_type="webhook",
            payload={"target_url": ep.url},
            settings=settings,
        )

        assert res["status"] == "success"
        assert res["details"]["http_status"] == 200
        assert "signature" in res["details"]
        assert mock_post.called

        # Verify call header had X-JKR-Signature
        call_kwargs = mock_post.call_args.kwargs
        assert "X-JKR-Signature" in call_kwargs["headers"]


@pytest.mark.asyncio
async def test_hubspot_crm_connect_and_test(memory_db: AsyncSession, test_workspace: Workspace):
    """Test 3: Verify real HubSpot API lead creation sync and honest rejection."""
    settings = get_settings()

    # 1. Success case: HubSpot creates contact (201 Created)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(201, json={"id": "hs-contact-998877", "properties": {}})

        res = await service.verify_and_connect_crm(
            memory_db,
            workspace_id=test_workspace.id,
            crm_type="hubspot",
            hubspot_token="pat-na1-valid-token-12345",
            crm_name="HubSpot",
            settings=settings,
        )

        assert res["status"] == "connected"
        assert res["provider"] == "hubspot"
        assert res["hubspot_id"] == "hs-contact-998877"

        # Verify catalog now reflects Connected HubSpot
        cat = await service.catalog(memory_db, workspace_id=test_workspace.id)
        crm_item = next(c for c in cat if c["type"] == "crm")
        assert crm_item["status"] == "connected"
        assert crm_item["external_url"] == "https://app.hubspot.com"
        assert "HubSpot" in crm_item["connected_account"]

    # 2. Run test runner for CRM
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(409, text="Contact already exists. Existing ID: 998877")

        test_res = await service.run_integration_test(
            memory_db,
            workspace_id=test_workspace.id,
            integration_type="crm",
            settings=settings,
        )
        assert test_res["status"] == "success"
        assert test_res["details"]["hubspot_id"] == "998877"

    # 3. Error case: Invalid token (HTTP 401) must reject without faking connected
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(401, text="Unauthorized: Invalid token")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.verify_and_connect_crm(
                memory_db,
                workspace_id=test_workspace.id,
                crm_type="hubspot",
                hubspot_token="pat-na1-invalid-token",
                crm_name="HubSpot",
                settings=settings,
            )
        assert exc_info.value.status_code == 400
        assert "Authentication Failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_calendar_ics_and_csv_test_runner(memory_db: AsyncSession, test_workspace: Workspace):
    """Test 4: Verify RFC 5545 .ics generation and CSV export pipeline."""
    # Calendar test runner
    cal_res = await service.run_integration_test(
        memory_db,
        workspace_id=test_workspace.id,
        integration_type="google_calendar",
    )
    assert cal_res["status"] == "success"
    assert "RFC 5545" in cal_res["message"]
    assert "google_calendar_url" in cal_res["details"]
    assert "https://calendar.google.com" in cal_res["details"]["google_calendar_url"]

    # CSV test runner
    csv_res = await service.run_integration_test(
        memory_db,
        workspace_id=test_workspace.id,
        integration_type="google_sheets",
    )
    assert csv_res["status"] == "success"
    assert "columns" in csv_res["details"]
    assert "download_url" in csv_res["details"]


@pytest.mark.asyncio
async def test_meta_whatsapp_n8n_honest_verification(memory_db: AsyncSession, test_workspace: Workspace):
    """Test 5: Verify Meta, WhatsApp, and n8n enforce honest verification and reject invalid credentials."""
    settings = get_settings()
    from fastapi import HTTPException

    # 1. Meta Lead Ads requires token
    with pytest.raises(HTTPException):
        await service.connect_meta_lead_ads(
            memory_db,
            workspace_id=test_workspace.id,
            page_id="page-12345",
            access_token="",
            settings=settings,
        )

    # 2. Meta verification with valid mock response
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"id": "page-12345", "name": "Dental Clinic FB Page"})
        meta_res = await service.connect_meta_lead_ads(
            memory_db,
            workspace_id=test_workspace.id,
            page_id="page-12345",
            access_token="valid_fb_token_123",
            settings=settings,
        )
        assert meta_res["status"] == "connected"
        assert meta_res["page_name"] == "Dental Clinic FB Page"

    # 3. WhatsApp Business requires WABA ID and token
    with pytest.raises(HTTPException):
        await service.connect_whatsapp_business(
            memory_db,
            workspace_id=test_workspace.id,
            phone_number="+919876543210",
            waba_id="",
            access_token="",
            settings=settings,
        )

    # 4. n8n verification succeeds on 200, fails on error
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = httpx.Response(200, json={"status": "ok"})
        n8n_res = await service.verify_and_connect_n8n(
            memory_db,
            workspace_id=test_workspace.id,
            instance_url="https://n8n.mycompany.com",
            api_key="key-123",
        )
        assert n8n_res["status"] == "connected"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        with pytest.raises(HTTPException):
            await service.verify_and_connect_n8n(
                memory_db,
                workspace_id=test_workspace.id,
                instance_url="https://broken-n8n.com",
                api_key="key-123",
            )
