"""P3.5 §34 connection-reuse fix, shared by every batch REST provider client
in this package (sarvam_stt.py, sarvam_tts.py) — each used to open a brand-
new httpx.AsyncClient (and TCP+TLS connection) per call. One process-
lifetime client instead, same pattern as jkr_conversation.llm_client and
jkr_db.embeddings use for the OpenAI-facing side of the same bug. See
docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md §3 for why this is a real
correctness fix with a modest (not dominant) measured latency effect.
"""

from __future__ import annotations

import httpx

_shared_client: httpx.AsyncClient | None = None


def get_shared_http_client(*, timeout: float = 20.0) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(timeout=timeout)
    return _shared_client
