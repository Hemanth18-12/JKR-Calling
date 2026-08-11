"""Text embeddings shared by the ingestion side (services/api, embeds
knowledge chunks) and the query side (voice-worker, embeds the customer's
question) — they MUST use the same function or cosine similarity between the
two is meaningless.

`mock_embed` is a real, deterministic, testable function — not a stub that
returns zeros — but it is a bag-of-hashed-words vector, not a real semantic
embedding: it will cluster chunks that share vocabulary, not chunks that
mean the same thing without sharing words. That is an honest, documented
limitation (spec's "mock providers" mandate, docs/DECISIONS/0002), not a
hidden one. `embed_text` swaps to a real OpenAI embedding call automatically
when `OPENAI_API_KEY` is set, without any caller-visible change.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

EMBEDDING_DIM = 1536
_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)

# P3.5 §34 — same connection-reuse fix as jkr_conversation.llm_client: one
# process-lifetime client instead of a new httpx.AsyncClient (and TCP+TLS
# handshake) per embedding call. See docs/CONVERSATION_ENGINE_LATENCY_AUDIT.md
# §3 for why this is a correctness fix with a modest, not dominant, measured
# effect on this specific network path.
_shared_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _shared_http_client
    import httpx

    if _shared_http_client is None:
        _shared_http_client = httpx.AsyncClient(timeout=15.0)
    return _shared_http_client


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def mock_embed(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    tokens = _tokenize(text)
    if not tokens:
        vector[0] = 1.0
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        # Two independent hash-derived slots per token reduces collision
        # damage from a single bucket, still O(1) and fully deterministic.
        idx_a = int.from_bytes(digest[0:4], "big") % EMBEDDING_DIM
        idx_b = int.from_bytes(digest[4:8], "big") % EMBEDDING_DIM
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        vector[idx_a] += sign
        vector[idx_b] += sign * 0.5

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


async def embed_text(text: str) -> list[float]:
    """Async so a real provider (network call) is a drop-in replacement."""
    if os.environ.get("OPENAI_API_KEY"):
        try:
            return await _openai_embed(text)
        except Exception:
            # Never let an embedding-provider hiccup break ingestion/retrieval
            # in a demo/local environment — fall back to the mock, which
            # always succeeds. A production deployment would alert on this
            # fallback rather than silently accept it call after call.
            pass
    return mock_embed(text)


async def _openai_embed(text: str) -> list[float]:
    api_key = os.environ["OPENAI_API_KEY"]
    client = _get_http_client()
    response = await client.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": "text-embedding-3-small", "input": text},
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]
