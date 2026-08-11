"""Signed, expiring media-session tokens — binds a Media Stream WebSocket
connection to a specific, already-created JKR call_session before any
audio is ever accepted. HMAC-SHA256 over a base64url JSON payload, the
same dependency-free style already used by app/security.py's CSRF token
(hmac.compare_digest, no itsdangerous) — reusing that pattern rather than
introducing a new signing dependency for one endpoint.

The WebSocket URL Twilio connects to carries this token
(wss://.../ws/twilio/media/{token}) instead of raw call_session_id/
workspace_id query params — per spec, the client (Twilio, or anyone who
can read a TwiML response) must never be trusted to assert its own
workspace/call identity; the server resolves everything from the signed
token instead. See docs/TWILIO_MEDIA_STREAMS.md.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass


class InvalidMediaTokenError(Exception):
    """One exception type for every failure mode (malformed, tampered,
    expired) deliberately — a caller branching on *which* failure it was
    would leak that distinction to an unauthenticated WebSocket client."""


@dataclass(frozen=True)
class MediaSessionTokenPayload:
    call_session_id: uuid.UUID
    workspace_id: uuid.UUID
    twilio_call_sid: str
    redis_state_token: str  # the same opaque per-call token already used as the Redis state key for voice/status/recording/closing-grace webhooks — carried here so the WS handler can look up business_identity/policy/recent_turns/tts_speaker without a second lookup mechanism
    issued_at: float
    expires_at: float


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_media_session_token(
    *, secret: str, call_session_id: uuid.UUID, workspace_id: uuid.UUID, twilio_call_sid: str, redis_state_token: str, ttl_seconds: int = 3600
) -> str:
    """ttl_seconds is generous (default 1hr) relative to how quickly Twilio
    actually connects after receiving the TwiML (seconds) — the token only
    needs to survive that gap, but expiry is checked once at connect time
    (see verify_media_session_token), not per-frame, so a long real call
    must never have its already-validated session invalidated mid-call by
    this same check."""
    now = time.time()
    payload = {
        "csid": str(call_session_id), "wsid": str(workspace_id), "tcs": twilio_call_sid, "rst": redis_state_token,
        "iat": now, "exp": now + ttl_seconds,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_media_session_token(token: str, *, secret: str) -> MediaSessionTokenPayload:
    try:
        payload_b64, signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise InvalidMediaTokenError("malformed token") from exc

    expected_signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise InvalidMediaTokenError("signature mismatch")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidMediaTokenError("malformed payload") from exc

    if time.time() > payload.get("exp", 0):
        raise InvalidMediaTokenError("token expired")

    try:
        return MediaSessionTokenPayload(
            call_session_id=uuid.UUID(payload["csid"]), workspace_id=uuid.UUID(payload["wsid"]),
            twilio_call_sid=payload["tcs"], redis_state_token=payload["rst"],
            issued_at=payload["iat"], expires_at=payload["exp"],
        )
    except (KeyError, ValueError) as exc:
        raise InvalidMediaTokenError("malformed payload fields") from exc
