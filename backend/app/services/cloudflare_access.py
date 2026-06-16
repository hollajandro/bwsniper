"""
Cloudflare Access JWT validation.

Cloudflare Tunnel/Access forwards authenticated requests to the origin with a
signed Cf-Access-Jwt-Assertion header. We validate that token before using any
identity claims from it.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from ..config import (
    CLOUDFLARE_ACCESS_AUD,
    CLOUDFLARE_ACCESS_ISSUER,
    CLOUDFLARE_ACCESS_JWKS_URL,
)


class CloudflareAccessConfigError(RuntimeError):
    pass


class CloudflareAccessTokenError(ValueError):
    pass


@dataclass(frozen=True)
class CloudflareIdentity:
    subject: str
    email: str
    name: str | None = None


def cloudflare_access_configured() -> bool:
    return bool(
        CLOUDFLARE_ACCESS_AUD
        and CLOUDFLARE_ACCESS_ISSUER
        and CLOUDFLARE_ACCESS_JWKS_URL
    )


def _audiences() -> list[str]:
    return [aud.strip() for aud in CLOUDFLARE_ACCESS_AUD.split(",") if aud.strip()]


def validate_cloudflare_access_jwt(token: str) -> CloudflareIdentity:
    if not cloudflare_access_configured():
        raise CloudflareAccessConfigError(
            "Cloudflare Access auth is enabled but CLOUDFLARE_ACCESS_AUD, "
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN or CLOUDFLARE_ACCESS_ISSUER, and "
            "CLOUDFLARE_ACCESS_JWKS_URL are not configured."
        )

    try:
        signing_key = PyJWKClient(CLOUDFLARE_ACCESS_JWKS_URL).get_signing_key_from_jwt(
            token
        )
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_audiences(),
            issuer=CLOUDFLARE_ACCESS_ISSUER,
        )
    except jwt.PyJWTError as ex:
        raise CloudflareAccessTokenError("Invalid Cloudflare Access token.") from ex

    subject = str(payload.get("sub") or "")
    email = str(payload.get("email") or "").strip().lower()
    name = (
        payload.get("name") or payload.get("given_name") or payload.get("common_name")
    )
    if not subject or not email:
        raise CloudflareAccessTokenError(
            "Cloudflare Access token is missing required identity claims."
        )

    return CloudflareIdentity(
        subject=subject,
        email=email,
        name=str(name) if name else None,
    )
