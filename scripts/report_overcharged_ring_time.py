"""Audit report script: Overcharged ring time on past calls (Prompt A Phase 1.1).

DO NOT RUN AUTOMATICALLY — This script is prepared for manual review by the owner.
It performs a read-only audit against Postgres to identify any past calls where
coins were charged for ring/dialing time (or unanswered calls that were charged),
calculates the exact overcharge per call, and provides a clear refund summary.

Usage (when ready to inspect):
    python scripts/report_overcharged_ring_time.py
    python scripts/report_overcharged_ring_time.py --export-csv refund_report.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "db"))

from jkr_db.session import get_session
from jkr_db.models.calls import CallSession
from jkr_db.models.coins import CoinTransaction, CoinWallet
from jkr_db.models.tenancy import Workspace
from sqlalchemy import select


async def run_audit_report(csv_export_path: str | None = None) -> None:
    print("=" * 80)
    print("JKR AI CALLING — COIN AUDIT REPORT: OVERCHARGED RING TIME (READ-ONLY)")
    print("=" * 80)

    async with get_session() as db:
        # Load all call deduction transactions
        tx_query = select(CoinTransaction).where(
            CoinTransaction.transaction_type == "call_deduction"
        ).order_by(CoinTransaction.created_at.desc())
        tx_res = await db.execute(tx_query)
        transactions = tx_res.scalars().all()

        if not transactions:
            print("No call deduction transactions found in the database.")
            return

        print(f"Auditing {len(transactions)} call deduction transactions...\n")

        # Load workspaces
        ws_res = await db.execute(select(Workspace.id, Workspace.name))
        workspaces = {str(row[0]): row[1] for row in ws_res.all()}

        overcharged_records = []
        total_overcharged_coins = 0

        for tx in transactions:
            if not tx.reference_id:
                continue

            try:
                call_res = await db.execute(
                    select(CallSession).where(CallSession.id == tx.reference_id)
                )
                call = call_res.scalar_one_or_none()
            except Exception:
                continue

            if not call:
                continue

            charged_coins = abs(tx.amount_coins)
            actual_billable_seconds = 0
            unanswered = call.status in {"no_answer", "busy", "failed", "canceled", "abandoned", "no-answer"} or call.answered_at is None

            if not unanswered and call.answered_at and call.ended_at:
                actual_billable_seconds = max(0, int((call.ended_at - call.answered_at).total_seconds()))

            overcharged_coins = max(0, charged_coins - actual_billable_seconds)

            if overcharged_coins > 0:
                total_overcharged_coins += overcharged_coins
                ws_name = workspaces.get(str(call.workspace_id), "Unknown")
                overcharged_records.append({
                    "call_id": str(call.id),
                    "workspace_id": str(call.workspace_id),
                    "workspace_name": ws_name,
                    "status": call.status,
                    "dialed_at": call.started_at.isoformat() if call.started_at else "N/A",
                    "answered_at": call.answered_at.isoformat() if call.answered_at else "N/A",
                    "ended_at": call.ended_at.isoformat() if call.ended_at else "N/A",
                    "coins_charged": charged_coins,
                    "actual_connected_seconds": actual_billable_seconds,
                    "overcharged_ring_coins": overcharged_coins,
                })

        print(f"Total Calls Audited:       {len(transactions)}")
        print(f"Overcharged Calls Found:   {len(overcharged_records)}")
        print(f"Total Overcharged Coins:   {total_overcharged_coins} coins (₹{total_overcharged_coins * 60 / 60} equivalent)\n")

        if overcharged_records:
            print(f"{'Call ID':<38} | {'Status':<12} | {'Charged':<8} | {'Actual(s)':<10} | {'Overcharge':<10} | Workspace")
            print("-" * 105)
            for r in overcharged_records[:20]:
                print(
                    f"{r['call_id']:<38} | {r['status']:<12} | {r['coins_charged']:<8} | "
                    f"{r['actual_connected_seconds']:<10} | {r['overcharged_ring_coins']:<10} | {r['workspace_name']}"
                )
            if len(overcharged_records) > 20:
                print(f"... and {len(overcharged_records) - 20} more records.")

            if csv_export_path:
                with open(csv_export_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(overcharged_records[0].keys()))
                    writer.writeheader()
                    writer.writerows(overcharged_records)
                print(f"\n[OK] Exported full audit to {csv_export_path}")
        else:
            print("✅ All past calls have 0 overcharge. Billing matches connected time.")

    print("=" * 80)
    print("NOTE: This script does NOT modify any balances or records.")
    print("=" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit past calls for overcharged ring time.")
    parser.add_argument("--export-csv", dest="export_csv", help="Path to write CSV report", default=None)
    args = parser.parse_args()
    asyncio.run(run_audit_report(args.export_csv))
