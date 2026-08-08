"""Password hashing, session token primitives, and the SSRF guard.

Session tokens: a cryptographically random opaque token is generated at login,
the RAW token is set in the httpOnly cookie, and only its SHA-256 hash is
persisted (Session.token_hash / Redis key) — this way a database/Redis leak
alone can never be replayed as a valid session. See docs/DECISIONS/0006-auth.md.

`encrypt_secret`/`decrypt_secret` live in `jkr_db.crypto`, not here — they're
pure/framework-agnostic and intelligence-worker needs the same implementation
to decrypt a webhook signing secret (see jkr_db.webhook_engine). Re-exported
here so existing call sites in this service don't need to know that.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, status
from jkr_db.crypto import decrypt_secret, encrypt_secret

__all__ = [
    "SSRFBlockedError",
    "assert_public_host",
    "decrypt_secret",
    "encrypt_secret",
    "generate_csrf_token",
    "generate_session_token",
    "hash_password",
    "hash_session_token",
    "needs_rehash",
    "verify_csrf_token",
    "verify_password",
]

_hasher = PasswordHasher()


class SSRFBlockedError(HTTPException):
    def __init__(self, url: str):
        super().__init__(status.HTTP_400_BAD_REQUEST, f"Refusing to fetch/register {url!r}: resolves to a non-public address")


def assert_public_host(hostname: str, url: str) -> None:
    """SSRF guard (docs/SECURITY_AND_COMPLIANCE.md §7): resolve the hostname
    and reject loopback/private/link-local/reserved ranges before ever
    issuing a request to (or registering) a user-supplied URL — checking the
    URL string alone (e.g. blocking "localhost") is not enough, since a
    hostname can resolve to a private IP regardless of what it's spelled
    like. Shared by knowledge-ingestion's website fetcher and integrations'
    webhook-endpoint registration — both are "this server will make a
    network request to a URL a user typed in," the same trust boundary."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not resolve host: {hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise SSRFBlockedError(url)


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, raw_password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_csrf_token(session_token_hash: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), session_token_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf_token(session_token_hash: str, secret: str, candidate: str) -> bool:
    expected = generate_csrf_token(session_token_hash, secret)
    return hmac.compare_digest(expected, candidate)
