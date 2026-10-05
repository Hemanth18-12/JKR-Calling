#!/usr/bin/env python3
"""JKR Calling Native Model Context Protocol (MCP) Server.

Enables AI agents and IDEs (Cursor, Claude Desktop, Antigravity) to:
- Inspect agents & prompts
- Dispatch live voice calls
- Query coin wallet balances & usage transactions
- Retrieve call logs & transcripts
- Generate website voice/chat widget embed codes
- Book appointments

Transport: JSON-RPC 2.0 over standard I/O (stdio).
Zero external dependencies required.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("jkr_mcp")

DEFAULT_API_BASE = os.getenv("JKR_API_BASE", "http://localhost:8000").rstrip("/")
JKR_API_KEY = os.getenv("JKR_API_KEY", "")
DEFAULT_WORKSPACE_ID = os.getenv("JKR_WORKSPACE_ID", "")


def _call_api(path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
    """Internal HTTP request helper calling the JKR Calling backend API."""
    url = f"{DEFAULT_API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "JKR-MCP-Server/1.0",
    }
    if JKR_API_KEY:
        headers["Authorization"] = f"Bearer {JKR_API_KEY}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("detail") or err_json.get("message") or err_body
        except Exception:
            msg = err_body
        raise RuntimeError(f"JKR API Error ({err.code}): {msg}") from err
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to JKR Calling API at {url}: {exc}") from exc


TOOLS = [
    {
        "name": "jkr_list_agents",
        "description": "Lists all voice AI agents in the JKR Calling workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Optional workspace UUID. Defaults to environment default.",
                }
            },
        },
    },
    {
        "name": "jkr_get_agent",
        "description": "Gets detailed configuration, voice persona, and prompt versions for an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "The UUID of the agent."},
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "jkr_dispatch_call",
        "description": "Dispatches an outbound AI phone call to a customer using Dograh conversation workflow & Sarvam TTS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "UUID of the agent to place the call."},
                "phone_number": {"type": "string", "description": "Destination phone number in E.164 format (e.g. +919876543210)."},
                "customer_name": {"type": "string", "description": "Name of the recipient customer."},
            },
            "required": ["agent_id", "phone_number"],
        },
    },
    {
        "name": "jkr_get_wallet_balance",
        "description": "Retrieves the workspace Coin Wallet balance, recent top-up requests, and usage deductions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace UUID."},
            },
        },
    },
    {
        "name": "jkr_list_call_logs",
        "description": "Lists recent live and mock call sessions, statuses, durations, and costs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max sessions to return (default 10)."},
            },
        },
    },
    {
        "name": "jkr_get_call_transcript",
        "description": "Fetches the full turn-by-turn spoken transcript of a specific call session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Call session UUID."},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "jkr_get_widget_code",
        "description": "Generates the ready-to-use HTML/React embed code to place a voice & chat widget on any website.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent UUID to embed."},
                "theme_color": {"type": "string", "description": "Hex color code (e.g. #4f46e5)."},
                "position": {"type": "string", "enum": ["bottom-right", "bottom-left"], "description": "Position on screen."},
                "language": {"type": "string", "enum": ["te-IN", "hi-IN", "en-IN"], "description": "Default language."},
            },
            "required": ["agent_id"],
        },
    },
]


def handle_call_tool(name: str, args: dict[str, Any]) -> Any:
    """Dispatches tool execution."""
    if name == "jkr_list_agents":
        ws_id = args.get("workspace_id") or DEFAULT_WORKSPACE_ID
        res = _call_api(f"/api/v1/agents?workspace_id={ws_id}" if ws_id else "/api/v1/agents")
        return {"agents": res}

    elif name == "jkr_get_agent":
        agent_id = args["agent_id"]
        res = _call_api(f"/api/v1/agents/{agent_id}")
        return res

    elif name == "jkr_dispatch_call":
        payload = {
            "agent_id": args["agent_id"],
            "to_phone_e164": args["phone_number"],
            "metadata": {"customer_name": args.get("customer_name", "Customer")},
        }
        res = _call_api("/api/v1/calls/dispatch", method="POST", data=payload)
        return {
            "status": "dispatched",
            "session_id": res.get("id"),
            "call_sid": res.get("provider_call_id"),
        }

    elif name == "jkr_get_wallet_balance":
        ws_id = args.get("workspace_id") or DEFAULT_WORKSPACE_ID
        res = _call_api(f"/api/v1/coins/wallet?workspace_id={ws_id}" if ws_id else "/api/v1/coins/wallet")
        return res

    elif name == "jkr_list_call_logs":
        limit = args.get("limit", 10)
        res = _call_api(f"/api/v1/calls?limit={limit}")
        return {"calls": res}

    elif name == "jkr_get_call_transcript":
        session_id = args["session_id"]
        res = _call_api(f"/api/v1/calls/{session_id}/transcript")
        return res

    elif name == "jkr_get_widget_code":
        agent_id = args["agent_id"]
        theme_color = args.get("theme_color", "#4f46e5")
        position = args.get("position", "bottom-right")
        language = args.get("language", "te-IN")

        html_code = (
            f"<!-- JKR Calling AI Voice Widget -->\n"
            f'<script src="{DEFAULT_API_BASE}/jkr-widget.js"\n'
            f'  data-agent-id="{agent_id}"\n'
            f'  data-theme-color="{theme_color}"\n'
            f'  data-position="{position}"\n'
            f'  data-language="{language}"\n'
            f'  data-api-base="{DEFAULT_API_BASE}"\n'
            f"  async>\n"
            f"</script>"
        )
        return {
            "html_code": html_code,
            "agent_id": agent_id,
            "theme_color": theme_color,
            "position": position,
            "language": language,
        }

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    """Main stdio JSON-RPC loop for Model Context Protocol."""
    logger.info("JKR Calling Native MCP Server started on stdio")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        response: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}

        try:
            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "jkr-calling-mcp",
                        "version": "1.0.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                }

            elif method == "tools/list":
                response["result"] = {"tools": TOOLS}

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                result_data = handle_call_tool(tool_name, tool_args)
                response["result"] = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result_data, indent=2, ensure_ascii=False),
                        }
                    ]
                }

            elif method == "ping":
                response["result"] = {}

            else:
                response["error"] = {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                }

        except Exception as exc:
            logger.exception("Error executing MCP method %s", method)
            response["error"] = {
                "code": -32603,
                "message": str(exc),
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
