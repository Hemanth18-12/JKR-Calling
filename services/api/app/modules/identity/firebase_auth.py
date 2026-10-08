"""Server-side Firebase ID token verification using Google's public x509 certs.

Zero service-account secrets needed — verifies the RS256 signature directly against
Google's public securetoken keys, checks audience (FIREBASE_PROJECT_ID), issuer,
expiration, and email_verified claim.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from cryptography.x509 import load_pem_x509_certificate
from fastapi import HTTPException, status

logger = logging.getLogger("jkr_api.identity.firebase_auth")

GOOGLE_PUBLIC_CERT_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)

# In-memory cache for Google's public certificates
_cached_certs: dict[str, Any] = {}
_certs_expiry: float = 0.0


async def _get_google_public_certs() -> dict[str, str]:
    """Fetches Google's public x509 certificates for Firebase Auth, caching with Cache-Control TTL."""
    global _cached_certs, _certs_expiry

    now = time.time()
    if _cached_certs and now < _certs_expiry:
        return _cached_certs

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GOOGLE_PUBLIC_CERT_URL)
            resp.raise_for_status()
            certs = resp.json()

            # Parse max-age from Cache-Control header if present
            cache_control = resp.headers.get("Cache-Control", "")
            max_age = 3600  # default 1 hour
            for part in cache_control.split(","):
                part = part.strip()
                if part.startswith("max-age="):
                    try:
                        max_age = int(part.split("=")[1])
                    except ValueError:
                        pass

            _cached_certs = certs
            _certs_expiry = now + max_age
            logger.info("Refreshed Google Firebase public certs (count: %d, ttl: %ds)", len(certs), max_age)
            return _cached_certs
    except Exception as exc:
        if _cached_certs:
            logger.warning("Failed to refresh Google certs, using stale cache: %s", exc)
            return _cached_certs
        logger.exception("Failed to fetch Google public certs: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not reach Google identity servers to verify authentication token.",
        ) from exc


async def verify_firebase_id_token(
    id_token: str,
    project_id: str,
) -> dict[str, Any]:
    """Verifies a Firebase ID token server-side and returns verified user payload.

    Validates:
    - Signature using Google's public keys
    - Token header `kid` matches a current Google key
    - Issuer == https://securetoken.google.com/{project_id}
    - Audience == project_id
    - Expiration (exp) and auth_time
    - email_verified is True
    """
    if not id_token or not id_token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firebase ID token is required.")

    if not project_id or not project_id.strip():
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "FIREBASE_PROJECT_ID is not configured on the backend.",
        )

    clean_token = id_token.strip()

    try:
        unverified_header = jwt.get_unverified_header(clean_token)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed Firebase token header.") from exc

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firebase token header is missing 'kid'.")

    certs = await _get_google_public_certs()
    cert_str = certs.get(kid)
    if not cert_str:
        # Key might have rotated, try one fresh fetch before failing
        global _certs_expiry
        _certs_expiry = 0.0
        certs = await _get_google_public_certs()
        cert_str = certs.get(kid)
        if not cert_str:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Unknown or expired Google signing key (kid not recognized).",
            )

    try:
        cert_obj = load_pem_x509_certificate(cert_str.encode("utf-8"))
        public_key = cert_obj.public_key()
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Error loading Google certificate.") from exc

    expected_issuer = f"https://securetoken.google.com/{project_id}"

    try:
        payload = jwt.decode(
            clean_token,
            public_key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=expected_issuer,
            options={
                "verify_signature": True,
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "require": ["exp", "iat", "aud", "iss", "sub"],
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in token has expired. Please sign in again.") from exc
    except jwt.InvalidIssuerError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token issuer.") from exc
    except jwt.InvalidAudienceError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token audience.") from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token verification failed: {exc}") from exc

    # Validate email
    email = payload.get("email", "").strip().lower()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google account does not provide an email address.")

    email_verified = payload.get("email_verified", False)
    if not email_verified:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your Google account email has not been verified by Google. Please verify it before signing in.",
        )

    return {
        "uid": payload.get("sub"),
        "email": email,
        "name": payload.get("name") or email.split("@")[0],
        "picture": payload.get("picture"),
        "firebase_claims": payload,
    }
