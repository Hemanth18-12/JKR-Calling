"""Scripted walkthrough of the spec §33 demo flow against a running stack.

Run via `make demo` (after `make setup && make seed` and starting every
service — see README.md/Makefile's `dev-native` target). Logs into the
seeded Aaha Dental Care workspace, creates a fresh contact + campaign each
run (so the script is safely re-runnable — the one campaign `make seed`
itself creates is meant for a human to click through in the UI, not to be
consumed by this script), and drives it through: consent → campaign →
dry-run (safety gate) → launch → the dialer loop actually calling and
booking an appointment → post-call intelligence → analytics.

No real outbound call is ever placed — every workspace's telephony provider
defaults to mock (docs/DECISIONS/0003-safety-gate-independent-of-dry-run.md).
"""

from __future__ import annotations

import asyncio
import sys
import time as time_module

import httpx

API_BASE = "http://localhost:8000/api/v1"
OWNER_EMAIL = "owner@aahadentalcare.demo"
OWNER_PASSWORD = "DemoPassword123!"


def _step(label: str) -> None:
    print(f"\n=== {label} ===")


async def _require_2xx(response: httpx.Response, context: str) -> dict:
    if response.status_code >= 400:
        print(f"FAILED at {context}: {response.status_code} {response.text}", file=sys.stderr)
        raise SystemExit(1)
    return response.json() if response.content else {}


async def main() -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
        _step("1. Log in as the seeded Aaha Dental Care owner")
        login = await _require_2xx(
            await client.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}), "login"
        )
        print(f"  Logged in as {login['full_name']}")

        me = await _require_2xx(await client.get("/auth/me"), "me")
        workspace_id = me["active_workspace_id"]
        print(f"  Active workspace: {workspace_id}")

        _step("2. Confirm the seeded agent is published and knowledge is approved")
        agents = await _require_2xx(await client.get("/agents", params={"workspace_id": workspace_id}), "list agents")
        agent = next(a for a in agents if a["status"] == "active")
        print(f"  Agent: {agent['name']} (published_version_id={agent['published_version_id'] is not None})")

        documents = await _require_2xx(await client.get("/knowledge/documents", params={"workspace_id": workspace_id}), "list docs")
        approved_docs = [d for d in documents if d["approval_state"] == "approved"]
        print(f"  Approved knowledge documents: {len(approved_docs)}")

        _step("3. Create a fresh contact and record consent")
        suffix = str(int(time_module.time()))[-5:]
        contact = await _require_2xx(
            await client.post(
                "/contacts", params={"workspace_id": workspace_id},
                json={"full_name": f"Demo Contact {suffix}", "phone": f"98765{suffix}"},
            ),
            "create contact",
        )
        print(f"  Contact: {contact['full_name']} ({contact['phone_masked']})")

        await _require_2xx(
            await client.post(
                f"/contacts/{contact['id']}/consent", params={"workspace_id": workspace_id},
                json={"purpose": "marketing", "source": "verbal_recorded"},
            ),
            "record consent",
        )
        print("  Consent recorded (marketing)")

        _step("4. Create a book_appointment campaign and add the contact")
        campaign = await _require_2xx(
            await client.post(
                "/campaigns", params={"workspace_id": workspace_id},
                json={"name": f"Demo Run {suffix}", "objective": "book_appointment", "agent_id": agent["id"], "max_attempts": 3},
            ),
            "create campaign",
        )
        print(f"  Campaign: {campaign['name']} (status={campaign['status']})")

        await _require_2xx(
            await client.post(
                f"/campaigns/{campaign['id']}/contacts", params={"workspace_id": workspace_id},
                json={"contact_ids": [contact["id"]]},
            ),
            "add contacts",
        )

        _step("5. Dry-run the safety gate (no side effects)")
        dry_run = await _require_2xx(
            await client.post(f"/campaigns/{campaign['id']}/dry-run", params={"workspace_id": workspace_id}), "dry-run"
        )
        print(f"  Would dispatch: {dry_run['would_dispatch']}/{dry_run['evaluated']}")
        for result in dry_run["results"]:
            print(f"    {result['contact_name']}: would_dispatch={result['would_dispatch']} failed_check={result['failed_check']}")

        if dry_run["would_dispatch"] == 0:
            blocked_reason = dry_run["results"][0]["failed_check"]
            if blocked_reason == "calling_hours":
                print("  Outside the workspace's configured calling hours (09:00-20:00 IST) right now —")
                print("  widening this campaign's window for this demo run only, then re-checking.")
                await _require_2xx(
                    await client.patch(
                        f"/campaigns/{campaign['id']}/schedule", params={"workspace_id": workspace_id},
                        json={"calling_window_start": "00:00:00", "calling_window_end": "23:59:00"},
                    ),
                    "widen schedule",
                )
                dry_run = await _require_2xx(
                    await client.post(f"/campaigns/{campaign['id']}/dry-run", params={"workspace_id": workspace_id}), "dry-run retry"
                )
                print(f"  Would dispatch (after widening): {dry_run['would_dispatch']}/{dry_run['evaluated']}")
            else:
                print(f"  Blocked by '{blocked_reason}' — cannot proceed with the demo call.", file=sys.stderr)
                raise SystemExit(1)

        _step("6. Launch the campaign — campaign-worker's dialer loop takes over")
        launched = await _require_2xx(
            await client.post(f"/campaigns/{campaign['id']}/launch", params={"workspace_id": workspace_id}), "launch"
        )
        print(f"  Campaign status: {launched['status']}")

        _step("7. Wait for the mock call to run and the campaign to complete")
        for attempt in range(30):
            await asyncio.sleep(2)
            current = await _require_2xx(await client.get(f"/campaigns/{campaign['id']}", params={"workspace_id": workspace_id}), "poll campaign")
            counts = {c["status"]: c["count"] for c in current["contact_counts"]}
            print(f"  [{attempt * 2}s] campaign={current['status']} contact_counts={counts}")
            if current["status"] in ("completed", "failed", "cancelled"):
                break
        else:
            print("  Timed out waiting for the campaign to finish.", file=sys.stderr)
            raise SystemExit(1)

        _step("8. Verify the appointment was booked and follow-up sent")
        appointments = await _require_2xx(await client.get("/appointments", params={"workspace_id": workspace_id}), "list appointments")
        matching = [a for a in appointments if a["contact_id"] == contact["id"]]
        if matching:
            appt = matching[0]
            print(f"  Appointment: {appt['scheduled_for']} ({appt['status']})")
        else:
            print("  No appointment booked for this contact (objective may not have completed).")

        # The campaign shows "completed" as soon as the dialer finishes its
        # last attempt, but post-call intelligence (which creates and
        # dispatches the FollowUpTask) runs as a separate async job enqueued
        # moments earlier — a real, small eventual-consistency gap, not a
        # bug. Poll briefly rather than reporting "no follow-up" on a race.
        matching_followups: list[dict] = []
        for _ in range(5):
            follow_ups = await _require_2xx(await client.get("/follow-ups", params={"workspace_id": workspace_id}), "list follow-ups")
            matching_followups = [f for f in follow_ups if f["contact_id"] == contact["id"]]
            if matching_followups:
                break
            await asyncio.sleep(1)
        for f in matching_followups:
            print(f"  Follow-up: {f['channel']} -> {f['status']}")
        if not matching_followups:
            print("  No follow-up task found yet for this contact.")

        _step("9. Analytics reflect the run")
        overview = await _require_2xx(await client.get("/analytics/overview", params={"workspace_id": workspace_id}), "analytics overview")
        print(f"  total_calls={overview['total_calls']} connect_rate={overview['connect_rate']} appointments_booked={overview['appointments_booked']}")

        print("\nDemo flow complete — no real outbound call was ever placed (mock provider throughout).")


if __name__ == "__main__":
    asyncio.run(main())
