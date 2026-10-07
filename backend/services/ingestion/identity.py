"""Signed device-identity cookie (INGT-02, D-01, D-02).

D-01: a server-issued device/session identifier in an HttpOnly cookie is
sufficient for INGT-02's attribution requirement -- no account, no email
(D-02), no password. 02-RESEARCH.md Pitfall 4: a signing secret with a
public/shared default provides zero security, which is why the secret is
resolved through `resolve_device_id_cookie_secret()` rather than a literal.
Threat T-02-01: a forged or replayed cookie could evade rate limiting --
`itsdangerous`'s own signature verification (never a hand-rolled HMAC
comparison, which is a timing-attack surface) closes this.

Purpose limitation (privacy prohibition): this identifier exists solely to
key rate limiting (Phase 2 Plan 04) and, in Phase 5, to enforce one
corroboration per report per identity (EVID-04). It must NOT be used for
cross-report behavioural profiling and must NOT be surfaced to citizens or
in any public API response. It is also a stable, long-lived identifier,
not anonymity -- any future UI copy describing submissions as anonymous
would contradict this implementation.
"""

import functools
import uuid

import itsdangerous
from fastapi import Request, Response
from itsdangerous import URLSafeTimedSerializer

from backend.core.config import resolve_device_id_cookie_secret, settings

# Explicit purpose-scoping salt: a value signed for some other future
# cookie cannot be replayed as a device identity.
COOKIE_SALT = "roadtwin-device-id"


@functools.lru_cache(maxsize=1)
def _get_serializer() -> URLSafeTimedSerializer:
    """Lazy + memoized so an unset secret does not raise at import time."""
    return URLSafeTimedSerializer(resolve_device_id_cookie_secret(), salt=COOKIE_SALT)


def read_or_mint_device_id(raw_cookie: str | None) -> tuple[str, str | None]:
    """Returns `(device_id, new_signed_cookie_value_or_None)`.

    Never raises and never represents a bad cookie as a client error: a
    tampered, foreign-secret or expired cookie is handled identically to a
    missing one, so a citizen whose browser blocks or discards cookies (or
    whose cookie merely expired) is never blocked from submitting.
    """
    if raw_cookie is not None:
        try:
            device_id = _get_serializer().loads(
                raw_cookie, max_age=settings.device_id_cookie_max_age_seconds
            )
            return device_id, None
        except itsdangerous.BadSignature:
            # Covers both a tampered/foreign-secret signature and an
            # expired one (SignatureExpired subclasses BadSignature).
            pass

    device_id = str(uuid.uuid4())
    signed_value = _get_serializer().dumps(device_id)
    return device_id, signed_value


def set_device_cookie(response: Response, signed_value: str) -> None:
    response.set_cookie(
        key=settings.device_id_cookie_name,
        value=signed_value,
        httponly=True,
        secure=settings.device_id_cookie_secure,
        samesite="lax",
        max_age=settings.device_id_cookie_max_age_seconds,
        path="/",
    )


async def get_device_identity(response: Response, request: Request) -> str:
    """FastAPI dependency: returns the bare device id, never the signed blob."""
    raw_cookie = request.cookies.get(settings.device_id_cookie_name)
    device_id, new_signed_value = read_or_mint_device_id(raw_cookie)
    if new_signed_value is not None:
        set_device_cookie(response, new_signed_value)
    return device_id
