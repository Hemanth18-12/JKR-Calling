"""Dograh Telephony Client for live calls.

Integrates JKR Calling with Dograh (https://github.com/dograh-hq/dograh)
telephony gateway for placing outbound calls and managing call state.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger("jkr_api.dograh_telephony")


class DograhNotConfiguredError(RuntimeError):
    pass


class DograhTelephonyClient:
    def __init__(self, *, api_url: str, api_key: str = ""):
        if not api_url:
            raise DograhNotConfiguredError("DOGRAH_API_URL is not configured")
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def create_call(
        self,
        *,
        to: str,
        from_number: str,
        workflow_id: str = "kelly_assistant",
        initial_context: dict[str, Any] | None = None,
    ) -> str:
        """Initiates an outbound call via Dograh's /telephony/initiate-call endpoint."""
        payload = {
            "phone_number": to,
            "from_phone_number_id": from_number,
            "workflow_id": workflow_id,
            "initial_context": initial_context or {},
        }
        async with httpx.AsyncClient(base_url=self._api_url, timeout=15.0) as client:
            response = await client.post(
                "/telephony/initiate-call",
                json=payload,
                headers=self._headers(),
            )
            if response.is_error:
                logger.error(f"Dograh initiate-call failed with status {response.status_code}: {response.text}")
                response.raise_for_status()
            data = response.json()
            return data.get("call_id") or data.get("workflow_run_id") or f"dograh-call-{uuid.uuid4()}"

    async def hangup_call(self, *, call_id: str) -> None:
        async with httpx.AsyncClient(base_url=self._api_url, timeout=5.0) as client:
            try:
                await client.post(
                    f"/telephony/calls/{call_id}/hangup",
                    headers=self._headers(),
                )
            except Exception as exc:
                logger.warning(f"Failed to hangup call {call_id} in Dograh: {exc}")
