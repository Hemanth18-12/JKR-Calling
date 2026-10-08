import datetime
import hashlib
import time
import uuid
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from app.config import Settings
from app.modules.tenancy import service as tenancy_service
from jkr_db.models.identity import User, PasswordCredential
from jkr_db.models.tenancy import Organization, Workspace, WorkspaceMember, WorkspaceInvitation, Role


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            User.metadata.create_all,
            tables=[
                User.__table__,
                PasswordCredential.__table__,
                Organization.__table__,
                Workspace.__table__,
                WorkspaceMember.__table__,
                WorkspaceInvitation.__table__,
                Role.__table__,
            ],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        # Seed owner and member roles
        owner_role = Role(
            id=uuid.uuid4(),
            key="workspace_owner",
            name="Workspace Owner",
            description="Owner",
        )
        operator_role = Role(
            id=uuid.uuid4(),
            key="agent_operator",
            name="Agent Operator",
            description="Operator",
        )
        session.add(owner_role)
        session.add(operator_role)
        await session.flush()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_team_invitations_full_lifecycle(memory_db: AsyncSession):
    test_settings = Settings(
        app_base_url="http://localhost:3000",
        api_base_url="http://localhost:8000",
    )

    # 1. Create owner user and workspace
    owner = User(
        id=uuid.uuid4(),
        email="owner@jkr.ai",
        full_name="Workspace Owner",
    )
    memory_db.add(owner)
    await memory_db.flush()

    org = Organization(id=uuid.uuid4(), name="Test Org")
    memory_db.add(org)
    await memory_db.flush()

    workspace = Workspace(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="Apollo Clinic",
        slug="apollo-clinic",
    )
    memory_db.add(workspace)
    await memory_db.flush()

    owner_role = (
        await memory_db.execute(select(Role).where(Role.key == "workspace_owner"))
    ).scalar_one()

    owner_member = WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=owner.id,
        role_id=owner_role.id,
        status="active",
        joined_at=datetime.datetime.now(datetime.timezone.utc),
    )
    memory_db.add(owner_member)
    await memory_db.flush()

    # 2. Invite a new teammate: invitee@example.com
    invited_email = "invitee@example.com"
    with patch(
        "app.modules.tenancy.service.send_invitation_email",
        new=AsyncMock(return_value=(True, "")),
    ) as mock_send_email:
        invitation_dict = await tenancy_service.invite_member(
            memory_db,
            workspace_id=workspace.id,
            inviter=owner,
            email=invited_email,
            role_key="agent_operator",
            settings=test_settings,
        )

        assert mock_send_email.called
        call_kwargs = mock_send_email.call_args.kwargs
        assert call_kwargs["to_email"] == invited_email
        assert call_kwargs["workspace_name"] == "Apollo Clinic"
        assert "token=" in call_kwargs["invite_url"]

        # Extract raw token from invite url to test acceptance
        raw_token = call_kwargs["invite_url"].split("token=")[1]
        invitation_id = invitation_dict["id"]

    # 3. Verify owner sees member listed as "invited"
    members = await tenancy_service.list_members(memory_db, workspace_id=workspace.id)
    assert len(members) == 2  # 1 active owner + 1 invited member
    invited_entry = next(m for m in members if m["email"] == invited_email)
    assert invited_entry["status"] == "invited"
    assert invited_entry["invitation_id"] == invitation_id

    # 4. Verify in-app listing for invited user
    pending = await tenancy_service.list_pending_invitations_for_user(
        memory_db, user_email=invited_email
    )
    assert len(pending) == 1
    assert pending[0]["workspace_name"] == "Apollo Clinic"
    assert pending[0]["role_key"] == "agent_operator"

    # 5. Public token verification check
    details = await tenancy_service.get_invitation_details_by_token(
        memory_db, token=raw_token
    )
    assert details["workspace_name"] == "Apollo Clinic"
    assert details["email"] == invited_email

    # 6. Attempt acceptance with WRONG user email -> 403 Forbidden
    intruder_user = User(
        id=uuid.uuid4(),
        email="intruder@malicious.com",
        full_name="Intruder Person",
    )
    memory_db.add(intruder_user)
    await memory_db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await tenancy_service.accept_invitation(
            memory_db,
            current_user=intruder_user,
            token=raw_token,
        )
    assert exc_info.value.status_code == 403
    assert "This invitation was sent to" in exc_info.value.detail

    # 7. Accept invitation with the LEGITIMATE invited user
    legit_user = User(
        id=uuid.uuid4(),
        email=invited_email,
        full_name="Legit Teammate",
    )
    memory_db.add(legit_user)
    await memory_db.flush()

    accept_result = await tenancy_service.accept_invitation(
        memory_db,
        current_user=legit_user,
        token=raw_token,
    )
    assert accept_result["success"] is True
    assert accept_result["workspace_id"] == workspace.id

    # Check database: user is now an active member
    mem_row = (
        await memory_db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == legit_user.id,
            )
        )
    ).scalar_one_or_none()
    assert mem_row is not None
    assert mem_row.status == "active"

    # Check invitation is marked accepted
    inv_row = (
        await memory_db.execute(
            select(WorkspaceInvitation).where(
                WorkspaceInvitation.id == invitation_id
            )
        )
    ).scalar_one()
    assert inv_row.status == "accepted"
    assert inv_row.accepted_by_user_id == legit_user.id

    # 8. Attempting to accept a reused token fails
    with pytest.raises(HTTPException) as exc_info:
        await tenancy_service.accept_invitation(
            memory_db,
            current_user=legit_user,
            token=raw_token,
        )
    assert exc_info.value.status_code == 400
    assert "already accepted" in exc_info.value.detail

    # 9. Verify members table now reflects 2 ACTIVE members
    members_after = await tenancy_service.list_members(
        memory_db, workspace_id=workspace.id
    )
    assert len(members_after) == 2
    assert all(m["status"] == "active" for m in members_after)


@pytest.mark.asyncio
async def test_team_invitations_resend_and_revoke(memory_db: AsyncSession):
    test_settings = Settings(
        app_base_url="http://localhost:3000",
        api_base_url="http://localhost:8000",
    )

    owner = User(id=uuid.uuid4(), email="boss@jkr.ai", full_name="The Boss")
    memory_db.add(owner)
    await memory_db.flush()

    org = Organization(id=uuid.uuid4(), name="Boss Org")
    memory_db.add(org)
    await memory_db.flush()

    ws = Workspace(id=uuid.uuid4(), organization_id=org.id, name="Boss Workspace", slug="boss-ws")
    memory_db.add(ws)
    await memory_db.flush()

    with patch(
        "app.modules.tenancy.service.send_invitation_email",
        new=AsyncMock(return_value=(True, "")),
    ):
        inv = await tenancy_service.invite_member(
            memory_db,
            workspace_id=ws.id,
            inviter=owner,
            email="someone@example.com",
            role_key="agent_operator",
            settings=test_settings,
        )
        inv_id = inv["id"]

        # Resend invitation
        resent = await tenancy_service.resend_invitation(
            memory_db,
            workspace_id=ws.id,
            invitation_id=inv_id,
            inviter=owner,
            settings=test_settings,
        )
        assert resent["status"] == "pending"

        # Revoke invitation
        await tenancy_service.revoke_invitation(
            memory_db,
            workspace_id=ws.id,
            invitation_id=inv_id,
        )

        # Check DB status is revoked
        db_inv = (
            await memory_db.execute(
                select(WorkspaceInvitation).where(WorkspaceInvitation.id == inv_id)
            )
        ).scalar_one()
        assert db_inv.status == "revoked"

        # Acceptance after revoke must fail
        dummy_user = User(id=uuid.uuid4(), email="someone@example.com", full_name="Someone")
        memory_db.add(dummy_user)
        await memory_db.flush()

        with pytest.raises(HTTPException) as exc_info:
            await tenancy_service.accept_invitation(
                memory_db,
                current_user=dummy_user,
                invitation_id=inv_id,
            )
        assert exc_info.value.status_code == 400
        assert "revoked" in exc_info.value.detail
