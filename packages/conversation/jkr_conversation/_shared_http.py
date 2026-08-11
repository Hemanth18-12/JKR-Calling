"""Shared httpx.AsyncClient singleton for every OpenAI-facing call in this
package (llm_client.py's batch calls, streaming_llm.py's streamed calls) —
same connection-reuse fix P3.5 established (see llm_client.py's own
docstring for the measured-effect caveat), extracted into its own module
so llm_client.py and streaming_llm.py can both depend on it without either
depending on the other. Mirrors services/api/app/live_providers/
_shared_http.py's identical pattern for the Sarvam-facing clients.
"""

from __future__ import annotations

import httpx

_shared_client: httpx.AsyncClient | None = None


def get_shared_http_client(*, timeout: float = 15.0) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(timeout=timeout)
    return _shared_client
