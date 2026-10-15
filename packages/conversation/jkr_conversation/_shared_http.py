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
    import asyncio

    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if _shared_client is None or _shared_client.is_closed or getattr(_shared_client, "_loop", None) not in (None, loop):
        _shared_client = httpx.AsyncClient(timeout=timeout)
        setattr(_shared_client, "_loop", loop)
    return _shared_client
