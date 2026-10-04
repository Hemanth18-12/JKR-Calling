from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from jkr_db.base import Base, TenantMixin


class CoinWallet(Base, TenantMixin):
    __tablename__ = "coin_wallets"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_coin_wallets_workspace_id"),
    )

    balance_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_recharged_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_spent_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CoinTopupRequest(Base, TenantMixin):
    __tablename__ = "coin_topup_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier_id: Mapped[str] = mapped_column(String(64), nullable=False)
    price_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    base_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    bonus_coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    screenshot_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class CoinTransaction(Base, TenantMixin):
    __tablename__ = "coin_transactions"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    amount_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
