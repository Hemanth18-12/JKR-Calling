"""Dograh Voice Engine Provider Adapter.

Integrates JKR AI Calling's voice worker with Dograh (https://github.com/dograh-hq/dograh),
providing low-latency real-time voice streaming with native Sarvam STT/TTS (Telugu, Hindi, English)
and telephony integrations (Twilio, Exotel).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.providers.base import (
    CallHandle,
    CallStatusInfo,
    MediaSession,
    NotConfiguredError,
    SynthesisResult,
    TranscriptResult,
    VoiceConfig,
)

logger = logging.getLogger("voice-worker.dograh")


@dataclass
class DograhTelephony:
    """Telephony provider backed by Dograh's telephony gateway (Twilio / Exotel)."""

    api_url: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_URL", "http://dograh-api:8000")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_KEY", "")
    )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def create_outbound_call(
        self, *, to: str, from_: str, context: dict[str, Any]
    ) -> CallHandle:
        payload = {
            "to": to,
            "from": from_,
            "initial_context": context,
            "workflow_id": context.get("workflow_id", "kelly_assistant"),
        }
        async with httpx.AsyncClient(base_url=self.api_url, timeout=10.0) as client:
            try:
                resp = await client.post(
                    "/telephony/initiate-call",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                call_ref = data.get("call_id", f"dograh-call-{uuid.uuid4()}")
                return CallHandle(provider_call_ref=call_ref, raw=data)
            except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
                logger.warning(f"Dograh initiate-call failed ({exc}), falling back to direct reference")
                return CallHandle(provider_call_ref=f"dograh-pending-{uuid.uuid4()}", raw={"error": str(exc)})

    async def accept_inbound_call(self, *, call_ref: str) -> CallHandle:
        return CallHandle(provider_call_ref=call_ref)

    async def end_call(self, *, call_ref: str) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                await client.post(
                    f"/telephony/calls/{call_ref}/hangup",
                    headers=self._headers(),
                )
            except Exception as e:
                logger.warning(f"Failed to hangup call {call_ref} in Dograh: {e}")

    async def transfer_call(self, *, call_ref: str, target: str) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                await client.post(
                    f"/telephony/calls/{call_ref}/transfer",
                    json={"target": target},
                    headers=self._headers(),
                )
            except Exception as e:
                logger.warning(f"Failed to transfer call {call_ref} in Dograh: {e}")

    async def get_call_status(self, *, call_ref: str) -> CallStatusInfo:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"/telephony/calls/{call_ref}/status",
                    headers=self._headers(),
                )
                if resp.status_code == 200:
                    return CallStatusInfo(status=resp.json().get("status", "in-progress"), raw=resp.json())
            except Exception:
                pass
        return CallStatusInfo(status="completed")


@dataclass
class DograhMediaRuntime:
    """MediaRuntime adapter connecting JKR voice worker to Dograh's streaming engine."""

    api_url: str = field(
        default_factory=lambda: os.getenv("DOGRAH_API_URL", "http://dograh-api:8000")
    )
    sessions: dict[str, MediaSession] = field(default_factory=dict)

    async def create_session(self, *, call_id: str) -> MediaSession:
        session = MediaSession(session_id=f"dograh-session-{call_id}")
        self.sessions[call_id] = session
        return session

    async def publish_audio(self, *, session: MediaSession, chunk: bytes) -> None:
        # In Dograh, audio flows directly via WebSockets between the telephony carrier
        # (Twilio/Exotel) and Pipecat's Sarvam STT/TTS pipeline.
        return None

    async def cancel_output(self, *, session: MediaSession) -> None:
        async with httpx.AsyncClient(base_url=self.api_url, timeout=2.0) as client:
            try:
                await client.post(f"/sessions/{session.session_id}/cancel-output")
            except Exception:
                pass
