"""Audit script for Phase 1.1 (Money and access correctness).
Prepares a non-destructive dry-run report listing past calls that were overcharged
for ring time (dialed-to-answered window) before connected-window billing was enforced.

DO NOT EXECUTE MUTATIONS — DRY RUN AUDIT ONLY.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from jkr_db.models.calls import CallSession
from jkr_db.models.coins import CoinTransaction, CoinWallet
from jkr_db.models.tenancy import Workspace
from jkr_db.session import get_engine
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

IST = ZoneInfo("Asia/Kolkata")


async def generate_overcharge_audit():
    print("=" * 80)
    print("JKR AI Calling — Ring-Time Overcharge Audit Report (DRY-RUN)")
    print("=" * 80)
    print(f"Timestamp: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("Policy: Billing must strictly start at 'answered_at' and end at 'ended_at'.")
    print("Ring time (dialed to answered) must cost 0 coins.")
    print("Unanswered / busy / failed calls must cost 0 coins.")
    print("-" * 80)

    engine = get_engine()
    overcharged_records = []
    total_overcharged_coins = 0
    workspace_refund_summary: dict[str, int] = {}

    async with AsyncSession(engine) as session:
        # Fetch completed call sessions
        res = await session.execute(
            select(CallSession, Workspace.name)
            .join(Workspace, Workspace.id == CallSession.workspace_id)
            .order_by(CallSession.started_at.desc())
        )
        rows = res.all()

        for call, ws_name in rows:
            started = call.started_at
            answered = call.answered_at
            ended = call.ended_at
            billed_seconds = call.duration_seconds or 0

            if billed_seconds == 0:
                continue

            # Case A: Call was never answered, but had a non-zero duration billed
            if answered is None:
                overcharge_seconds = billed_seconds
                reason = "Unanswered call was billed"
            # Case B: Call was answered, but billed duration exceeded connected duration
            elif ended and answered:
                connected_seconds = max(0, int((ended - answered).total_seconds()))
                if billed_seconds > connected_seconds:
                    overcharge_seconds = billed_seconds - connected_seconds
                    reason = f"Ring time billed ({overcharge_seconds}s before pickup)"
                else:
                    continue
            else:
                continue

            overcharged_records.append({
                "call_id": str(call.id),
                "workspace_id": str(call.workspace_id),
                "workspace_name": ws_name,
                "started_at": started.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if started else "—",
                "answered_at": answered.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if answered else "Never",
                "ended_at": ended.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S") if ended else "—",
                "billed_seconds": billed_seconds,
                "overcharge_coins": overcharge_seconds,
                "reason": reason,
            })
            total_overcharged_coins += overcharge_seconds
            ws_key = f"{ws_name} ({call.workspace_id})"
            workspace_refund_summary[ws_key] = workspace_refund_summary.get(ws_key, 0) + overcharge_seconds

    if not overcharged_records:
        print("\n✅ Zero ring-time overcharges detected! All past calls adhere to the connected window.\n")
        return

    print(f"\nFound {len(overcharged_records)} call(s) with ring-time overcharges:\n")
    print(f"{'Call ID':<36} | {'Workspace':<20} | {'Answered (IST)':<19} | {'Billed':<6} | {'Overcharge Coins':<16} | {'Reason'}")
    print("-" * 120)
    for rec in overcharged_records:
        print(
            f"{rec['call_id']:<36} | {rec['workspace_name'][:18]:<20} | {rec['answered_at']:<19} | "
            f"{rec['billed_seconds']:<6} | {rec['overcharge_coins']:<16} | {rec['reason']}"
        )

    print("\n" + "=" * 80)
    print("PROPOSED REFUND SUMMARY BY WORKSPACE (DO NOT EXECUTE WITHOUT APPROVAL):")
    print("=" * 80)
    for ws_label, coins in workspace_refund_summary.items():
        print(f"  • {ws_label}: +{coins:,} Coins")
    print(f"\nTotal Potential Coins to Refund: {total_overcharged_coins:,} Coins")
    print("=" * 80)
    print("STATUS: Audit complete. No changes made to database.\n")


if __name__ == "__main__":
    asyncio.run(generate_overcharge_audit())
