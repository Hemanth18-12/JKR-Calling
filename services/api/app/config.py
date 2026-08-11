from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to the repo root, not left as a bare relative ".env" — pydantic-
# settings resolves a relative env_file against the process's current
# working directory, not this file's location. Every documented native
# startup command (`cd services/api && uv run ... uvicorn ...`) runs with
# CWD=services/api, where no .env file exists, so the relative form
# silently loads nothing and every setting falls back to its hardcoded
# default (enable_live_calls=False, etc.) — a real bug that shipped
# earlier, confirmed by loading Settings() from services/api and observing
# enable_live_calls come back False despite the root .env saying true.
# Docker Compose is unaffected either way (it injects real env vars via its
# own `env_file: .env` directive, which always outranks this field), and
# pytest's CWD is already the repo root, so this only changes behavior for
# the native-startup case it fixes.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_REPO_ROOT / ".env"), extra="ignore")

    app_env: str = "local"
    app_base_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    voice_worker_base_url: str = "http://localhost:8100"

    database_url: str = "postgresql+asyncpg://jkr_app:jkr_app_local_dev@localhost:55432/jkr_ai_calling"
    redis_url: str = "redis://localhost:16379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "jkr_minio"
    s3_secret_access_key: str = "jkr_minio_local_dev"
    s3_bucket_recordings: str = "jkr-recordings"
    s3_bucket_documents: str = "jkr-documents"
    s3_bucket_exports: str = "jkr-exports"
    s3_region: str = "ap-south-1"
    s3_force_path_style: bool = True

    session_secret: str = "change_me_dev_only_session_secret"
    csrf_secret: str = "change_me_dev_only_csrf_secret"
    credentials_encryption_key: str = "change_me_dev_only_fernet_key_44_bytes_base64"
    internal_service_token: str = "change_me_dev_only_service_to_service_token"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:3000/auth/oauth/google/callback"

    enable_live_calls: bool = False
    authorized_test_numbers: str = ""

    # --- Live real-call test path (app/modules/live_call) — additive, off by
    # default; see docs comment in .env.example. ---
    public_webhook_base_url: str = ""  # e.g. an ngrok https URL; falls back to api_base_url
    llm_provider_default: str = "mock"
    openai_api_key: str = ""
    telephony_provider_default: str = "mock"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    sarvam_tts_api_key: str = ""
    sarvam_api_key: str = ""

    # --- P3.5: ConversationEngine latency optimization ---
    # "legacy" (default, per spec §7's own recommendation) is byte-identical
    # to pre-P3.5 behavior — jkr_conversation.engine.process_turn() never
    # even calls fast_router when this is the value in effect. "fast"
    # enables the deterministic FastTurnRouter and the canned-response fast
    # path for safe ASK_FIELD/CLARIFY/CONFIRM_FIELD/DEFER_QUESTION turns —
    # see docs/P3_5_CONVERSATION_ENGINE_RESULTS.md.
    conversation_engine_mode: str = "legacy"  # "legacy" | "fast"

    # --- P2: Media Streams transport (docs/TWILIO_MEDIA_STREAMS.md) ---
    # "record" (default, unchanged existing behavior) keeps every real call
    # on the already-proven <Record>-based path in live_call/service.py.
    # "media_stream" routes new calls onto the persistent bidirectional
    # WebSocket transport instead — opt-in per environment until it has
    # real-call parity, never silently switched.
    twilio_voice_transport: str = "record"  # "record" | "media_stream"
    # What to do if TWILIO_VOICE_TRANSPORT=media_stream but the WebSocket
    # never gets a valid Twilio `start` event within the connect timeout —
    # "fail" ends the call with a clear error (the safe default: a silent,
    # undebuggable mid-call transport switch is worse than a failed call);
    # "fallback_record" is opt-in for environments that would rather
    # degrade than fail outright.
    twilio_media_stream_failure_policy: str = "fail"  # "fail" | "fallback_record"
    voice_media_debug: bool = False  # verbose per-frame logging (never raw audio) — see transport/events.py

    # --- P3: streaming STT (docs/SARVAM_STREAMING_STT_CONTRACT.md) ---
    # "batch" (default) keeps transitional_bridge.py's per-turn REST STT
    # call — unchanged existing behavior. "streaming" only has any effect
    # when TWILIO_VOICE_TRANSPORT=media_stream (streaming STT needs a
    # persistent audio connection that <Record> mode doesn't have); with
    # transport=record it's silently ignored — see effective_stt_mode.
    stt_mode: str = "batch"  # "batch" | "streaming"
    # What to do if the persistent Sarvam streaming connection fails to
    # connect at all, or drops mid-call and exhausts its bounded reconnect
    # attempts — "fail" ends the call (the safe default, same reasoning as
    # twilio_media_stream_failure_policy); "batch_next_turn" falls back to
    # the proven transitional_bridge.py turn-buffer path for the rest of
    # the call rather than dropping the customer entirely.
    stt_stream_failure_policy: str = "fail"  # "fail" | "batch_next_turn"

    @property
    def effective_stt_mode(self) -> str:
        """streaming STT has no meaning without a persistent audio
        transport — silently degrading to batch under <Record> mode is
        safer than a config combination nothing implements."""
        if self.stt_mode == "streaming" and self.twilio_voice_transport == "media_stream":
            return "streaming"
        return "batch"

    # --- P6: streaming TTS (docs/STREAMING_TTS_ARCHITECTURE.md) ---
    # "batch" (default) reproduces pre-P6 behavior exactly — one REST
    # SarvamTTS.synthesize() call on the complete reply text per turn,
    # unchanged. "streaming" opens a persistent Sarvam TTS WebSocket per
    # call and feeds it P5 SpeakableChunks (or a locally-chunked already-
    # known reply for canned/fast-path turns) so audio can start before
    # the whole utterance is synthesized. Only meaningful under
    # TWILIO_VOICE_TRANSPORT=media_stream — see effective_tts_mode.
    tts_mode: str = "batch"  # "batch" | "streaming"
    # What to do when the streaming TTS connection fails mid-response —
    # "batch_fallback" (default) falls back to a single batch REST
    # synthesize() call on the same text IF no audio was sent yet for that
    # response (spec §71); if some audio already played, no automatic
    # replay is attempted either way (spec §72), regardless of this
    # setting. "fail" ends the call outright, matching every other
    # provider-failure policy's most conservative option.
    tts_stream_failure_policy: str = "batch_fallback"  # "batch_fallback" | "fail"

    @property
    def effective_tts_mode(self) -> str:
        """Same reasoning as effective_stt_mode: streaming TTS needs the
        persistent bidirectional WebSocket Media Streams provides — under
        TWILIO_VOICE_TRANSPORT=record there's no live connection to stream
        audio into, so silently stay on "batch" rather than accept a
        configuration combination nothing implements (spec §13)."""
        if self.tts_mode == "streaming" and self.twilio_voice_transport == "media_stream":
            return "streaming"
        return "batch"

    # --- P4: turn detection (docs/TURN_DETECTION_ARCHITECTURE.md) ---
    # "provider" (default) reproduces pre-P4 behavior exactly — an STT final
    # commits immediately, no TurnManager delay/coalescing/semantic gating.
    # "vad": local-VAD-silence-timing-driven commit, no semantic gating —
    # benchmark mode. "hybrid": the full signal-weighing design (VAD +
    # provider events + semantic completeness + adaptive delay) — the
    # likely production direction after benchmarking, never auto-enabled.
    turn_detection_mode: str = "provider"  # "provider" | "vad" | "hybrid"
    turn_profile: str = "balanced"  # "fast" | "balanced" | "patient" — informational under "provider"
    local_vad_enabled: bool = False  # only meaningful under "vad"/"hybrid"; forwarding audio through EnergyVAD is skipped entirely otherwise

    @property
    def effective_turn_detection_mode(self) -> str:
        """Same reasoning as effective_stt_mode: turn detection modes other
        than "provider" only have meaning under streaming STT (they react
        to Sarvam's partial/final/speech events) — under STT_MODE=batch
        there is no persistent event stream for a TurnManager to consume,
        so silently stay on "provider" rather than accept a configuration
        combination nothing implements."""
        if self.turn_detection_mode in ("vad", "hybrid") and self.effective_stt_mode == "streaming":
            return self.turn_detection_mode
        return "provider"

    # --- P5: streaming LLM response generation (docs/STREAMING_LLM_ARCHITECTURE.md) ---
    # "complete" (default) is byte-identical to pre-P5 behavior —
    # prompt_builder.generate() always awaits llm_client.complete_text() and
    # returns the full response in one piece. "streaming" routes eligible
    # free-generation turns (never SAFETY_STOP/HUMAN_HANDOFF/
    # COMPLETE_OBJECTIVE/fast-path-eligible turns — those never call the LLM
    # at all, streaming or not) through StreamingResponseAssembler instead,
    # surfacing llm_ttft/llm_first_speakable_chunk/llm_full_generation into
    # the per-turn latency breakdown. TTS itself stays batch either way in
    # P5 — see docs/P5_STREAMING_LLM_RESULTS.md for what remains for P6.
    llm_response_mode: str = "complete"  # "complete" | "streaming"

    # --- P8: automatic barge-in (docs/BARGE_IN_ARCHITECTURE.md) ---
    # Defaults to False and MUST stay False until at least one authorized
    # real phone call has validated it (this phase's own explicit
    # instruction — automated tests cannot evaluate speaker echo, PSTN
    # noise, background TV, real "hmm" timing, or perceived Twilio clear
    # delay). Only has any effect at all when every prerequisite real-time
    # signal path is already active — see effective_barge_in_enabled.
    barge_in_enabled: bool = False
    # "low" | "balanced" | "high" — raw qualification-window/escalation
    # thresholds are deliberately not exposed as separate client-facing
    # settings (spec: "not raw thresholds exposed to normal clients"); see
    # turns/interruption_policy.py's _THRESHOLDS table. "high" must never be
    # the shipped default without real-call false-positive measurement.
    barge_in_sensitivity: str = "balanced"  # "low" | "balanced" | "high"
    # Spec — provider (LLM/TTS) cancellation must never hang the
    # interruption flow; a hung cancel still resolves the local state
    # transition on this timeout. See coordinator.py's
    # INTERRUPTION_CANCEL_TIMEOUT_SECONDS default (2000ms, same value).
    interruption_cancel_timeout_ms: int = 2000

    @property
    def effective_barge_in_enabled(self) -> bool:
        """Same cascading-gate reasoning as effective_stt_mode/
        effective_tts_mode/effective_turn_detection_mode: automatic
        barge-in has no meaning without a persistent audio connection,
        streamed TTS audio to actually interrupt, and real-time turn
        signals (VAD/provider speech events) to detect the interruption
        with — under any other combination there is nothing for it to
        orchestrate, so silently stay disabled rather than accept a
        configuration combination nothing implements."""
        if not self.barge_in_enabled:
            return False
        return (
            self.effective_stt_mode == "streaming"
            and self.effective_tts_mode == "streaming"
            and self.effective_turn_detection_mode in ("vad", "hybrid")
        )

    session_ttl_seconds: int = 60 * 60 * 24 * 14  # 14 days
    session_cookie_name: str = "jkr_session"

    default_workspace_daily_budget_paise: int = 500_000
    default_workspace_monthly_budget_paise: int = 10_000_000

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def authorized_test_numbers_list(self) -> list[str]:
        return [n.strip() for n in self.authorized_test_numbers.split(",") if n.strip()]

    @property
    def effective_public_webhook_base_url(self) -> str:
        return self.public_webhook_base_url or self.api_base_url

    @property
    def effective_media_stream_ws_base_url(self) -> str:
        """https://... -> wss://..., http://... -> ws://... (only the local
        dev case, never expected in a real Media Streams deployment — Twilio
        requires wss://). Twilio Media Streams requires a secure WebSocket
        for any real call; this only produces plain ws:// when
        PUBLIC_WEBHOOK_BASE_URL/API_BASE_URL itself is http://, which is a
        local-only configuration Twilio can never actually reach anyway."""
        base = self.effective_public_webhook_base_url
        if base.startswith("https://"):
            return "wss://" + base[len("https://") :]
        if base.startswith("http://"):
            return "ws://" + base[len("http://") :]
        return base


@lru_cache
def get_settings() -> Settings:
    return Settings()
