from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class CoinTier(BaseModel):
    id: str
    price_inr: int
    base_coins: int
    bonus_coins: int = 0
    total_coins: int
    label: str | None = None
    tag: str | None = None


COIN_TIERS: list[CoinTier] = [
    CoinTier(id="tier_100", price_inr=100, base_coins=300, bonus_coins=0, total_coins=300, label="Starter"),
    CoinTier(id="tier_250", price_inr=250, base_coins=800, bonus_coins=50, total_coins=850, label="Most Popular", tag="+50 Bonus"),
    CoinTier(id="tier_400", price_inr=400, base_coins=1350, bonus_coins=0, total_coins=1350, label="Pro Value"),
]


class CoinWalletOut(BaseModel):
    workspace_id: uuid.UUID
    balance_coins: int
    total_recharged_coins: int
    total_spent_coins: int


class CoinTopupRequestCreate(BaseModel):
    tier_id: str
    screenshot_base64: str = Field(..., min_length=1)
    screenshot_filename: str | None = None


class CoinTopupRequestOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    workspace_name: str | None = None
    user_id: uuid.UUID
    user_email: str | None = None
    tier_id: str
    price_inr: int
    base_coins: int
    bonus_coins: int
    total_coins: int
    screenshot_url: str
    status: str
    admin_notes: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class CoinTransactionOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    amount_coins: int
    transaction_type: str
    reference_id: str | None = None
    description: str
    balance_after: int
    created_at: datetime


class AdminReviewRequest(BaseModel):
    notes: str | None = None
