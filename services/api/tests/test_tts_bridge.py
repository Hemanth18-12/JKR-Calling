from __future__ import annotations

import asyncio
import uuid

from app.live_providers.streaming_tts import (
    StreamingTTSConfig,
    TTSAudioChunk,
    TTSCallContext,
    TTSCapabilities,
    TTSFailureClass,
    TTSFirstAudio,
    TTSGenerationCompleted,
    TTSStreamFailed,
)
from app.modules.live_call.transport.session import RealtimeMediaSession
from app.modules.live_call.transport.tts_bridge import (
    TTSStreamingSession,
    chunk_text_for_tts,
)


class _FakeProvider:
    """Deterministic fake: flush(response_id) immediately queues whatever
    events were pre-scripted for that response_id via `script()`, so tests
    can precisely control ordering/failure without real network timing."""

    def __init__(self):
        self.sent_texts: list[tuple[str, str, int]] = []
        self.flushes: list[str] = []
        self.cancelled: list[str] = []
        self._queue: asyncio.Queue = asyncio.Queue()
        self._scripts: dict[str, list] = {}

    def script(self, response_id: str, events: list) -> None:
        self._scripts[response_id] = events

    @property
    def capabilities(self):
        return TTSCapabilities(True, True, True, True, False, True, True, True)

    async def connect(self, *, config, context):
        pass

    async def send_text(self, *, text, response_id, chunk_index):
        self.sent_texts.append((text, response_id, chunk_index))

    async def flush(self, *, response_id):
        self.flushes.append(response_id)
        for event in self._scripts.get(response_id, [TTSGenerationCompleted(response_id=response_id)]):
            await self._queue.put(event)

    async def cancel(self, response_id):
        self.cancelled.append(response_id)

    async def close(self):
        pass

    async def events(self):
        while True:
            yield await self._queue.get()


def _make_media_session() -> RealtimeMediaSession:
    session = RealtimeMediaSession(call_session_id=uuid.uuid4(), workspace_id=uuid.uuid4(), twilio_call_sid="CA1")
    session.twilio_stream_sid = "MZ1"
    return session


async def _start_session(provider: _FakeProvider, media_session: RealtimeMediaSession) -> TTSStreamingSession:
    tts_session = TTSStreamingSession(provider=provider, media_session=media_session)
    await tts_session.start(config=StreamingTTSConfig(target_language_code="en-IN"), context=TTSCallContext(call_session_id="c", workspace_id="w"))
    return tts_session


def _audio(response_id: str, index: int, data: bytes = b"\xff\xff") -> TTSAudioChunk:
    return TTSAudioChunk(response_id=response_id, audio_chunk_index=index, data=data, content_type="audio/mulaw", codec="mulaw", sample_rate=8000)


# --- chunk_text_for_tts ------------------------------------------------


def test_chunk_text_for_tts_splits_on_sentence_boundaries():
    chunks = chunk_text_for_tts("First sentence. Second sentence.")
    assert chunks == ["First sentence.", "Second sentence."]


def test_chunk_text_for_tts_flushes_leftover_without_boundary():
    chunks = chunk_text_for_tts("No trailing punctuation")
    assert chunks == ["No trailing punctuation"]


# --- ordering ------------------------------------------------------------


async def test_text_sent_to_provider_in_order():
    provider = _FakeProvider()
    provider.script("resp_1", [TTSGenerationCompleted(response_id="resp_1")])
    tts_session = await _start_session(provider, _make_media_session())

    handle = tts_session.begin_response("resp_1")
    await handle.send_chunk("First.")
    await handle.send_chunk("Second.")
    await handle.send_chunk("Third.")
    await handle.finish()

    assert [t[0] for t in provider.sent_texts] == ["First.", "Second.", "Third."]
    assert [t[2] for t in provider.sent_texts] == [0, 1, 2]  # chunk_index strictly increasing
    await tts_session.close()


# --- finish() / completion --------------------------------------------------


async def test_finish_returns_final_mark_name_and_first_audio_ms():
    provider = _FakeProvider()
    provider.script("resp_1", [TTSFirstAudio(response_id="resp_1"), _audio("resp_1", 0), TTSGenerationCompleted(response_id="resp_1")])
    media_session = _make_media_session()
    tts_session = await _start_session(provider, media_session)

    handle = tts_session.begin_response("resp_1")
    await handle.send_chunk("Hello.")
    outcome = await handle.finish()

    assert outcome.failed is False
    assert outcome.chunks_sent == 1
    assert outcome.final_mark_name is not None
    assert outcome.first_audio_ms is not None and outcome.first_audio_ms >= 0
    assert media_session.outbound_queue.qsize() == 1
    queued = media_session.outbound_queue.get_nowait()
    assert queued.mark_name == outcome.final_mark_name
    assert queued.audio_is_mulaw_8k is True
    await tts_session.close()


async def test_failure_before_any_audio_reports_zero_chunks_sent():
    provider = _FakeProvider()
    provider.script("resp_1", [TTSStreamFailed(response_id="resp_1", failure_class=TTSFailureClass.PROVIDER_INTERNAL, message="down")])
    tts_session = await _start_session(provider, _make_media_session())

    handle = tts_session.begin_response("resp_1")
    await handle.send_chunk("Hello.")
    outcome = await handle.finish()

    assert outcome.failed is True
    assert outcome.chunks_sent == 0
    assert outcome.final_mark_name is None
    await tts_session.close()


async def test_failure_after_partial_audio_preserves_chunks_sent_and_mark():
    provider = _FakeProvider()
    provider.script("resp_1", [
        _audio("resp_1", 0), _audio("resp_1", 1),
        TTSStreamFailed(response_id="resp_1", failure_class=TTSFailureClass.STREAM_INTERRUPTED, message="dropped"),
    ])
    tts_session = await _start_session(provider, _make_media_session())

    handle = tts_session.begin_response("resp_1")
    await handle.send_chunk("Hello.")
    outcome = await handle.finish()

    assert outcome.failed is True
    assert outcome.chunks_sent == 2
    assert outcome.final_mark_name is not None  # the last successfully-enqueued chunk's mark, not discarded
    await tts_session.close()


# --- dead-connection timeout (spec §72 "never leave the caller in silence") -----


async def test_finish_times_out_rather_than_hanging_forever_if_no_completion_ever_arrives(monkeypatch):
    import app.modules.live_call.transport.tts_bridge as tts_bridge_mod

    monkeypatch.setattr(tts_bridge_mod, "RESPONSE_COMPLETION_TIMEOUT_SECONDS", 0.05)
    provider = _FakeProvider()
    # deliberately un-scripted: flush() will queue the default
    # TTSGenerationCompleted... so script an empty list to simulate a truly
    # dead connection that never produces ANY event for this response.
    provider.script("resp_1", [])
    tts_session = await _start_session(provider, _make_media_session())

    handle = tts_session.begin_response("resp_1")
    await handle.send_chunk("Hello.")
    outcome = await handle.finish()

    assert outcome.failed is True
    assert outcome.failure_message == "timeout_waiting_for_completion"
    assert outcome.chunks_sent == 0
    await tts_session.close()


# --- generation ownership / supersede --------------------------------------


async def test_begin_response_supersedes_unfinished_previous_response():
    provider = _FakeProvider()
    tts_session = await _start_session(provider, _make_media_session())

    handle_1 = tts_session.begin_response("resp_1")
    await handle_1.send_chunk("First response, never finished.")
    handle_2 = tts_session.begin_response("resp_2")  # starts before resp_1 finished

    outcome_1 = await handle_1.finish()
    assert outcome_1.failed is True
    assert outcome_1.failure_message == "superseded_by_new_response"
    await asyncio.sleep(0)  # let the fire-and-forget cancel() task run
    assert "resp_1" in provider.cancelled

    provider.script("resp_2", [TTSGenerationCompleted(response_id="resp_2")])
    outcome_2 = await handle_2.finish()
    assert outcome_2.failed is False
    await tts_session.close()


# --- isolation across two calls --------------------------------------------


async def test_two_tts_sessions_never_cross_response_ids_or_audio():
    provider_a, provider_b = _FakeProvider(), _FakeProvider()
    provider_a.script("resp_a", [_audio("resp_a", 0, data=b"\x01"), TTSGenerationCompleted(response_id="resp_a")])
    provider_b.script("resp_b", [_audio("resp_b", 0, data=b"\x02"), TTSGenerationCompleted(response_id="resp_b")])
    session_a, session_b = _make_media_session(), _make_media_session()
    tts_a = await _start_session(provider_a, session_a)
    tts_b = await _start_session(provider_b, session_b)

    handle_a = tts_a.begin_response("resp_a")
    handle_b = tts_b.begin_response("resp_b")
    await handle_a.send_chunk("A")
    await handle_b.send_chunk("B")
    outcome_a = await handle_a.finish()
    outcome_b = await handle_b.finish()

    assert outcome_a.response_id == "resp_a"
    assert outcome_b.response_id == "resp_b"
    chunk_a = session_a.outbound_queue.get_nowait()
    chunk_b = session_b.outbound_queue.get_nowait()
    assert chunk_a.response_sequence_id == "resp_a" and chunk_a.data == b"\x01"
    assert chunk_b.response_sequence_id == "resp_b" and chunk_b.data == b"\x02"
    await tts_a.close()
    await tts_b.close()
