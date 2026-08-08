"""Symmetric encryption for secrets at rest (provider credentials, webhook
signing secrets) — pure, framework-agnostic, so both services/api (which
encrypts a secret when a user submits one) and any worker that later needs
to decrypt one to use it (e.g. intelligence-worker signing a webhook
delivery) share the exact same implementation. `services/api/app/security.py`
re-exports these rather than redefining them.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet


@lru_cache
def _fernet(passphrase: str) -> Fernet:
    """Derives a valid Fernet key from an arbitrary CREDENTIALS_ENCRYPTION_KEY
    passphrase (which won't itself be in Fernet's required 32-byte
    urlsafe-base64 form) via SHA-256 — so `.env.example` can hold a plain
    memorable placeholder instead of requiring `Fernet.generate_key()` output.
    See docs/SECURITY_AND_COMPLIANCE.md §6 (provider credentials encrypted at
    rest; TODO in production: move this key into a real KMS)."""
    digest = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(raw_value: str, passphrase: str) -> str:
    return _fernet(passphrase).encrypt(raw_value.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted_value: str, passphrase: str) -> str:
    return _fernet(passphrase).decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
