"""Real Twilio client for the live real-call path: placing the outbound call
and validating that inbound webhook requests actually came from Twilio.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import httpx


class NotConfiguredError(RuntimeError):
    """Raised when Twilio credentials are absent — see openai_llm.NotConfiguredError."""


class TwilioClient:
    def __init__(self, *, account_sid: str, auth_token: str, from_number: str):
        if not (account_sid and auth_token and from_number):
            raise NotConfiguredError("Twilio credentials are not fully configured")
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    async def create_call(self, *, to: str, webhook_url: str, status_callback_url: str) -> str:
        async with httpx.AsyncClient(timeout=15.0, auth=(self._account_sid, self._auth_token)) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls.json",
                data={
                    "To": to,
                    "From": self._from_number,
                    "Url": webhook_url,
                    "Method": "POST",
                    "StatusCallback": status_callback_url,
                    "StatusCallbackMethod": "POST",
                    "StatusCallbackEvent": "completed",
                },
            )
        response.raise_for_status()
        return response.json()["sid"]


async def fetch_recording(*, account_sid: str, auth_token: str, recording_url: str) -> bytes:
    """Downloads a completed <Record> recording's audio bytes — Twilio's
    recording resource requires the same Basic Auth as every other REST call,
    and the plain RecordingUrl Twilio posts back needs a format suffix
    appended to fetch actual audio rather than the resource's JSON metadata."""
    url = recording_url if recording_url.endswith(".wav") else f"{recording_url}.wav"
    async with httpx.AsyncClient(timeout=20.0, auth=(account_sid, auth_token)) as client:
        response = await client.get(url)
    response.raise_for_status()
    return response.content


def validate_twilio_signature(*, auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    """Twilio's documented request-validation algorithm: HMAC-SHA1 of the
    exact webhook URL with every POST param (sorted by key, key+value
    concatenated with no delimiter) appended, keyed by the auth token,
    base64-encoded, compared to the X-Twilio-Signature header. This is the
    only thing standing between this public, unauthenticated endpoint and
    anyone on the internet POSTing fake call turns to it."""
    data = url
    for key in sorted(params.keys()):
        data += key + params[key]
    computed = base64.b64encode(hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")
    return hmac.compare_digest(computed, signature)
