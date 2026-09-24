"""MinIO / S3 object storage integration for JKR Calling platform.
Manages call recording audio persistence, full transcript JSON archives,
knowledge document uploads, and analytics export persistence.
"""

from __future__ import annotations

import io
import json
import logging
import os
import struct
import uuid
import wave
from datetime import timedelta
from typing import Any

import minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

DEFAULT_RECORDINGS_BUCKET = "jkr-recordings"
DEFAULT_DOCUMENTS_BUCKET = "jkr-documents"
DEFAULT_EXPORTS_BUCKET = "jkr-exports"

_client: minio.Minio | None = None


def get_minio_client() -> minio.Minio:
    """Return a singleton MinIO / S3 client configured from environment."""
    global _client
    if _client is not None:
        return _client

    raw_endpoint = os.environ.get("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    # Clean endpoint for minio client (remove http:// or https://)
    secure = raw_endpoint.startswith("https://")
    endpoint = raw_endpoint.replace("http://", "").replace("https://", "").rstrip("/")

    access_key = os.environ.get("S3_ACCESS_KEY_ID", "jkr_minio")
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY", "jkr_minio_local_dev")
    region = os.environ.get("S3_REGION", "us-east-1")

    _client = minio.Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=region,
    )
    return _client


def ensure_bucket(bucket_name: str = DEFAULT_RECORDINGS_BUCKET) -> None:
    """Ensure that the target bucket exists, creating it if necessary."""
    client = get_minio_client()
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info("Created MinIO bucket: %s", bucket_name)
    except Exception as exc:
        logger.warning("Could not verify/create bucket %s: %s", bucket_name, exc)


def upload_call_recording(
    workspace_id: uuid.UUID | str,
    call_id: uuid.UUID | str,
    audio_bytes: bytes,
    format: str = "wav",
    bucket: str = DEFAULT_RECORDINGS_BUCKET,
) -> str:
    """Upload call audio bytes to MinIO and return storage key."""
    client = get_minio_client()
    ensure_bucket(bucket)

    key = f"recordings/{workspace_id}/{call_id}.{format}"
    content_type = "audio/wav" if format == "wav" else "audio/mpeg"

    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=io.BytesIO(audio_bytes),
        length=len(audio_bytes),
        content_type=content_type,
    )
    logger.info("Persisted call recording to MinIO: %s/%s (%d bytes)", bucket, key, len(audio_bytes))
    return key


def upload_call_transcript(
    workspace_id: uuid.UUID | str,
    call_id: uuid.UUID | str,
    transcript_data: dict[str, Any] | str,
    bucket: str = DEFAULT_RECORDINGS_BUCKET,
) -> str:
    """Upload call transcript JSON to MinIO and return storage key."""
    client = get_minio_client()
    ensure_bucket(bucket)

    key = f"transcripts/{workspace_id}/{call_id}.json"
    if isinstance(transcript_data, dict):
        raw_text = json.dumps(transcript_data, indent=2, ensure_ascii=False)
    else:
        raw_text = transcript_data

    raw_bytes = raw_text.encode("utf-8")
    client.put_object(
        bucket_name=bucket,
        object_name=key,
        data=io.BytesIO(raw_bytes),
        length=len(raw_bytes),
        content_type="application/json; charset=utf-8",
    )
    logger.info("Persisted call transcript to MinIO: %s/%s (%d bytes)", bucket, key, len(raw_bytes))
    return key


def get_call_recording(
    workspace_id: uuid.UUID | str,
    call_id: uuid.UUID | str,
    format: str = "wav",
    bucket: str = DEFAULT_RECORDINGS_BUCKET,
) -> bytes | None:
    """Retrieve raw recording bytes from MinIO."""
    client = get_minio_client()
    key = f"recordings/{workspace_id}/{call_id}.{format}"
    try:
        response = client.get_object(bucket, key)
        return response.read()
    except Exception as exc:
        logger.warning("Failed to fetch recording %s/%s: %s", bucket, key, exc)
        return None


def get_call_transcript(
    workspace_id: uuid.UUID | str,
    call_id: uuid.UUID | str,
    bucket: str = DEFAULT_RECORDINGS_BUCKET,
) -> str | None:
    """Retrieve raw transcript text/json from MinIO."""
    client = get_minio_client()
    key = f"transcripts/{workspace_id}/{call_id}.json"
    try:
        response = client.get_object(bucket, key)
        return response.read().decode("utf-8")
    except Exception as exc:
        logger.warning("Failed to fetch transcript %s/%s: %s", bucket, key, exc)
        return None


def get_presigned_recording_url(
    workspace_id: uuid.UUID | str,
    call_id: uuid.UUID | str,
    format: str = "wav",
    bucket: str = DEFAULT_RECORDINGS_BUCKET,
    expires: timedelta = timedelta(hours=1),
) -> str:
    """Generate a presigned GET URL for secure direct browser playback."""
    client = get_minio_client()
    key = f"recordings/{workspace_id}/{call_id}.{format}"
    return client.presigned_get_object(bucket, key, expires=expires)


def generate_synthesized_call_audio(
    duration_seconds: int = 15,
    sample_rate: int = 16000,
    num_channels: int = 2,
) -> bytes:
    """Generate a valid stereo PCM WAV audio stream for the call session.
    Left channel: Agent audio carrier.
    Right channel: Customer audio carrier.
    """
    import math

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)

        total_frames = int(sample_rate * duration_seconds)
        samples = []
        for i in range(total_frames):
            t = i / sample_rate
            # Agent channel (440Hz modulated tone)
            agent_val = int(32767 * 0.2 * math.sin(2 * math.pi * 440 * t) * (1 if (int(t) % 4 < 2) else 0))
            # Customer channel (330Hz modulated tone)
            customer_val = int(32767 * 0.2 * math.sin(2 * math.pi * 330 * t) * (1 if (int(t) % 4 >= 2) else 0))
            samples.append(struct.pack("<hh", agent_val, customer_val))

        wf.writeframes(b"".join(samples))

    return buf.getvalue()
