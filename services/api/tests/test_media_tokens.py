from __future__ import annotations

import time
import uuid

import pytest
from app.modules.live_call.transport.media_tokens import (
    InvalidMediaTokenError,
    create_media_session_token,
    verify_media_session_token,
)

_SECRET = "test-secret"


def _token(**overrides) -> str:
    defaults = dict(
        secret=_SECRET, call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(),
        twilio_call_sid="CA123", redis_state_token="redis-tok-abc",
    )
    defaults.update(overrides)
    return create_media_session_token(**defaults)


def test_valid_token_round_trips():
    call_session_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    token = _token(call_session_id=call_session_id, workspace_id=workspace_id, twilio_call_sid="CA999", redis_state_token="rst-1")
    payload = verify_media_session_token(token, secret=_SECRET)
    assert payload.call_session_id == call_session_id
    assert payload.workspace_id == workspace_id
    assert payload.twilio_call_sid == "CA999"
    assert payload.redis_state_token == "rst-1"


def test_wrong_secret_rejected():
    token = _token()
    with pytest.raises(InvalidMediaTokenError):
        verify_media_session_token(token, secret="wrong-secret")


def test_tampered_payload_rejected():
    token = _token()
    payload_b64, signature = token.rsplit(".", 1)
    tampered = payload_b64 + "x." + signature  # corrupt the payload without recomputing the signature
    with pytest.raises(InvalidMediaTokenError):
        verify_media_session_token(tampered, secret=_SECRET)


def test_malformed_token_rejected():
    with pytest.raises(InvalidMediaTokenError):
        verify_media_session_token("not-a-real-token-at-all", secret=_SECRET)


def test_expired_token_rejected():
    token = _token(ttl_seconds=-1)  # already expired the instant it's created
    with pytest.raises(InvalidMediaTokenError):
        verify_media_session_token(token, secret=_SECRET)


def test_token_survives_within_ttl():
    token = _token(ttl_seconds=2)
    verify_media_session_token(token, secret=_SECRET)  # does not raise
    time.sleep(0.05)
    verify_media_session_token(token, secret=_SECRET)  # still valid shortly after
