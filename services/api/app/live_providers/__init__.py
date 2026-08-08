"""Real (non-mock) transport clients for the live real-call test path — see
app/modules/live_call. Conversation intelligence itself (extraction, RAG,
planning, response generation) no longer lives here or duplicates
services/voice-worker's logic — both call this real Twilio call and Test Lab
mock calls now share the exact same jkr_conversation engine. This package
covers only what's specific to a real phone call: Twilio telephony/webhook
signing, Sarvam TTS/STT — gated behind ENABLE_LIVE_CALLS + AUTHORIZED_TEST_NUMBERS
(see app/modules/live_call/service.py).
"""
