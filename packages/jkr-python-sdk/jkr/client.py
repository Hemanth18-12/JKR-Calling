"""JKR Calling Official Python SDK.

Zero-dependency Python client for JKR Calling:
- AI Voice Agent management
- Outbound Call Dispatching (Twilio + Dograh + Sarvam)
- Website Voice & Chat Widget sessions
- Coin Wallet Balance & Usage metering
- Call Transcripts & Analytics
"""

from __future__ import annotations

import json
import os
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


class JKRAPIError(Exception):
    """Raised when JKR Calling API returns an error."""

    def __init__(self, status_code: int, message: str, details: Any = None):
        self.status_code = status_code
        self.message = message
        self.details = details
        super().__init__(f"JKR API Error ({status_code}): {message}")


class JKRClient:
    """Main client interface for interacting with JKR Calling API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        workspace_id: str | None = None,
    ):
        self.api_key = api_key or os.getenv("JKR_API_KEY", "")
        self.base_url = (base_url or os.getenv("JKR_API_BASE", "http://localhost:8000")).rstrip("/")
        self.workspace_id = workspace_id or os.getenv("JKR_WORKSPACE_ID")

        self.agents = _AgentsService(self)
        self.calls = _CallsService(self)
        self.wallet = _WalletService(self)
        self.widget = _WidgetService(self)

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/api/v1{path}"
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                url = f"{url}?{urllib.parse.urlencode(clean_params)}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "JKR-Python-SDK/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8")
                if not content:
                    return {}
                return json.loads(content)
        except urllib.error.HTTPError as err:
            raw_err = err.read().decode("utf-8")
            try:
                err_data = json.loads(raw_err)
                msg = err_data.get("detail") or err_data.get("message") or err_data.get("error", {}).get("message") or raw_err
            except Exception:
                msg = raw_err
            raise JKRAPIError(err.code, msg, details=raw_err) from err
        except Exception as exc:
            raise RuntimeError(f"Connection failed to {url}: {exc}") from exc


class _AgentsService:
    def __init__(self, client: JKRClient):
        self.client = client

    def list(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        ws = workspace_id or self.client.workspace_id
        return self.client._request("GET", "/agents", params={"workspace_id": ws})

    def get(self, agent_id: str) -> dict[str, Any]:
        return self.client._request("GET", f"/agents/{agent_id}")


class _CallsService:
    def __init__(self, client: JKRClient):
        self.client = client

    def dispatch(
        self,
        agent_id: str,
        to_phone_e164: str,
        customer_name: str = "Customer",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "agent_id": agent_id,
            "to_phone_e164": to_phone_e164,
            "metadata": {**(metadata or {}), "customer_name": customer_name},
        }
        return self.client._request("POST", "/calls/dispatch", data=payload)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.client._request("GET", "/calls", params={"limit": limit})

    def get_transcript(self, session_id: str) -> dict[str, Any]:
        return self.client._request("GET", f"/calls/{session_id}/transcript")


class _WalletService:
    def __init__(self, client: JKRClient):
        self.client = client

    def get_balance(self, workspace_id: str | None = None) -> dict[str, Any]:
        ws = workspace_id or self.client.workspace_id
        return self.client._request("GET", "/coins/wallet", params={"workspace_id": ws})

    def list_transactions(self, workspace_id: str | None = None) -> list[dict[str, Any]]:
        ws = workspace_id or self.client.workspace_id
        return self.client._request("GET", "/coins/transactions", params={"workspace_id": ws})


class _WidgetService:
    def __init__(self, client: JKRClient):
        self.client = client

    def get_config(self, agent_id: str) -> dict[str, Any]:
        return self.client._request("GET", f"/widget/config/{agent_id}")

    def start_session(
        self,
        agent_id: str,
        visitor_name: str = "Website Visitor",
        visitor_phone: str | None = None,
        language: str = "te-IN",
    ) -> dict[str, Any]:
        return self.client._request(
            "POST",
            "/widget/session",
            data={
                "agent_id": agent_id,
                "visitor_name": visitor_name,
                "visitor_phone": visitor_phone,
                "language": language,
            },
        )

    def send_message(
        self,
        session_id: str,
        message: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        return self.client._request(
            "POST",
            f"/widget/session/{session_id}/message",
            data={"message": message, "language": language},
        )

    def end_session(self, session_id: str) -> dict[str, Any]:
        return self.client._request("POST", f"/widget/session/{session_id}/end")
