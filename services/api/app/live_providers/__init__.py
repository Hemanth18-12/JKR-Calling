"""Real (non-mock) provider clients for the live real-call test path — see
app/modules/live_call. Deliberately separate from services/voice-worker's
MockLLM/MockSTT/MockTTS/MockTelephony pipeline: that pipeline's conversation
logic is built around MockLLM's scripted-FSM methods (next_question,
closing_text, ...), not a general chat-completion loop, so a real LLM isn't a
drop-in swap there without a larger rework. This package instead backs a
small, additive, clearly-separate flow: one real outbound call, driven by
Twilio's own speech recognition/synthesis (<Gather>/<Say>) and a real LLM
chat completion per turn, gated behind ENABLE_LIVE_CALLS +
AUTHORIZED_TEST_NUMBERS (see app/modules/live_call/service.py).
"""
