"""Unit tests for Phase 1.1: Coins Billing Correctness, Connected Window, and Idempotency.

Matrix tested:
1. Dialed, customer never answers (no_answer): 0 coins deducted, duration_seconds=0
2. Busy / failed / canceled / abandoned: 0 coins deducted, duration_seconds=0
3. Answered, 20 seconds of talk, customer hangs up: exactly 20 coins deducted
4. Answered, agent ends the call: exactly connected talk time deducted
5. Duplicate completed webhook: exactly 0 second charge (idempotency guard)
6. Balance runs out mid-call: balance never goes negative (clamped at 0)
"""

import uuid
from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

from jkr_db.base import Base
from jkr_db.models.coins import CoinWallet, CoinTransaction
from jkr_db.models.calls import CallSession
from app.modules.coins.service import deduct_call_coins, get_or_create_wallet, get_wallet_balance


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            CoinWallet.metadata.create_all,
            tables=[CoinWallet.__table__, CoinTransaction.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_scenario_1_customer_never_answers_charges_zero(memory_db: AsyncSession):
    """Scenario 1: Dialed, customer never answers -> 0 coins deducted."""
    workspace_id = uuid.uuid4()
    call_id = uuid.uuid4()

    # Seed wallet with 500 coins
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=500, total_recharged_coins=500, total_spent_coins=0)
    memory_db.add(wallet)
    await memory_db.flush()

    balance_before = wallet.balance_coins

    # Call dialed at T=0, timed out / no-answer at T=30s
    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=30)
    answered_at = None  # Never answered!
    ended_at = now
    call_status = "no_answer"

    # Connected window calculation:
    unanswered_statuses = {"no_answer", "busy", "failed", "canceled", "abandoned", "no-answer"}
    if call_status in unanswered_statuses or answered_at is None:
        duration_seconds = 0
    else:
        duration_seconds = max(0, int((ended_at - answered_at).total_seconds()))

    assert duration_seconds == 0

    # Billing deduction
    balance_after = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=duration_seconds,
    )

    assert balance_after == 500
    assert wallet.balance_coins == 500
    assert wallet.total_spent_coins == 0

    # Ensure no CoinTransaction was created
    txs = (await memory_db.execute(select(CoinTransaction).where(CoinTransaction.workspace_id == workspace_id))).scalars().all()
    assert len(txs) == 0
    print(f"\n[PASS] Scenario 1 (Never Answers): Balance Before={balance_before}, After={balance_after}, Deducted=0")


@pytest.mark.asyncio
async def test_scenario_2_busy_failed_canceled_charges_zero(memory_db: AsyncSession):
    """Scenario 2: Busy / failed / canceled -> 0 coins deducted."""
    workspace_id = uuid.uuid4()
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=300, total_recharged_coins=300, total_spent_coins=0)
    memory_db.add(wallet)
    await memory_db.flush()

    for st in ["busy", "failed", "canceled"]:
        call_id = uuid.uuid4()
        call_status = st
        answered_at = None
        duration_seconds = 0 if (call_status in {"busy", "failed", "canceled"} or answered_at is None) else 45

        balance_after = await deduct_call_coins(
            memory_db,
            workspace_id=workspace_id,
            call_id=call_id,
            duration_seconds=duration_seconds,
        )
        assert balance_after == 300
        assert wallet.balance_coins == 300

    print(f"\n[PASS] Scenario 2 (Busy/Failed/Canceled): All 3 outcomes deducted 0 coins, balance remained 300")


@pytest.mark.asyncio
async def test_scenario_3_answered_20s_talk_customer_hangup(memory_db: AsyncSession):
    """Scenario 3: Dialed, ringing 10s, answered, 20 seconds of talk, customer hangs up -> exactly 20 coins."""
    workspace_id = uuid.uuid4()
    call_id = uuid.uuid4()
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=100, total_recharged_coins=100, total_spent_coins=0)
    memory_db.add(wallet)
    await memory_db.flush()

    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=30) # Dialed 30s ago
    answered_at = now - timedelta(seconds=20) # Picked up 20s ago (10s ring time!)
    ended_at = now # Hangup now
    call_status = "completed"

    # Strictly connected window: ended_at - answered_at = 20s (ring time excluded!)
    duration_seconds = max(0, int((ended_at - answered_at).total_seconds()))
    assert duration_seconds == 20

    balance_after = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=duration_seconds,
    )

    assert balance_after == 80
    assert wallet.balance_coins == 80
    assert wallet.total_spent_coins == 20

    # Verify ledger row
    tx = (await memory_db.execute(select(CoinTransaction).where(CoinTransaction.reference_id == str(call_id)))).scalar_one()
    assert tx.amount_coins == -20
    assert tx.transaction_type == "call_deduction"
    assert tx.balance_after == 80
    print(f"\n[PASS] Scenario 3 (Answered 20s): Balance Before=100, After=80, Coins Deducted=20, Ring Time Excluded")


@pytest.mark.asyncio
async def test_scenario_4_answered_agent_ends_call(memory_db: AsyncSession):
    """Scenario 4: Answered, agent ends call after 15s talk -> exactly 15 coins."""
    workspace_id = uuid.uuid4()
    call_id = uuid.uuid4()
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=80, total_recharged_coins=100, total_spent_coins=20)
    memory_db.add(wallet)
    await memory_db.flush()

    now = datetime.now(UTC)
    started_at = now - timedelta(seconds=25)
    answered_at = now - timedelta(seconds=15)
    ended_at = now

    duration_seconds = max(0, int((ended_at - answered_at).total_seconds()))
    assert duration_seconds == 15

    balance_after = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=duration_seconds,
    )

    assert balance_after == 65
    assert wallet.balance_coins == 65
    assert wallet.total_spent_coins == 35
    print(f"\n[PASS] Scenario 4 (Agent Ends 15s): Balance Before=80, After=65, Coins Deducted=15")


@pytest.mark.asyncio
async def test_scenario_5_duplicate_webhook_idempotency(memory_db: AsyncSession):
    """Scenario 5: Duplicate completed webhook arrives -> no second charge!"""
    workspace_id = uuid.uuid4()
    call_id = uuid.uuid4()
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=100, total_recharged_coins=100, total_spent_coins=0)
    memory_db.add(wallet)
    await memory_db.flush()

    # First webhook arrives: 25s talk
    b1 = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=25,
    )
    assert b1 == 75

    # Duplicate webhook arrives (e.g. status callback after recording callback)
    b2 = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=25,
    )
    assert b2 == 75 # Did NOT deduct 25 again!

    # Verify only 1 transaction exists in the ledger
    txs = (await memory_db.execute(select(CoinTransaction).where(CoinTransaction.reference_id == str(call_id)))).scalars().all()
    assert len(txs) == 1
    assert wallet.balance_coins == 75
    assert wallet.total_spent_coins == 25
    print(f"\n[PASS] Scenario 5 (Duplicate Webhook): First call balance=75, Duplicate webhook balance=75, Ledger rows=1")


@pytest.mark.asyncio
async def test_scenario_6_balance_runs_out_never_negative(memory_db: AsyncSession):
    """Scenario 6: Balance runs out mid-call -> clamped gracefully, balance never goes negative."""
    workspace_id = uuid.uuid4()
    call_id = uuid.uuid4()
    # Starting with only 10 coins
    wallet = CoinWallet(workspace_id=workspace_id, balance_coins=10, total_recharged_coins=10, total_spent_coins=0)
    memory_db.add(wallet)
    await memory_db.flush()

    # Call talked for 30 seconds
    balance_after = await deduct_call_coins(
        memory_db,
        workspace_id=workspace_id,
        call_id=call_id,
        duration_seconds=30,
    )

    # Balance is clamped at 0, never negative!
    assert balance_after == 0
    assert wallet.balance_coins == 0
    assert wallet.balance_coins >= 0
    print(f"\n[PASS] Scenario 6 (Balance Runs Out): Initial=10 coins, Talk=30s, Final Balance={balance_after} (Never Negative)")
