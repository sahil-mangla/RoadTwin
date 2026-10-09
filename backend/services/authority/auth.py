"""Authority staff authentication (AUTH-01, AUTH-02).

Staff log in with email + password (argon2 hashes) and receive a signed,
HttpOnly, SameSite=Lax session cookie. Every authority endpoint depends on
`require_staff`, which rejects a missing/invalid session (401) and any
account that is inactive or lacks the authority-staff role (403).

Mutating authority endpoints accept JSON bodies only, so a cross-site form
cannot submit them, and SameSite=Lax withholds the cookie from cross-site
POSTs -- together these cover CSRF for this deployment shape.

The failed-login throttle is in-process memory: it protects a single API
process. A multi-process deployment needs a shared store (e.g. Redis).
"""

from __future__ import annotations

import functools
import logging
import secrets
import time
import uuid
from collections import deque

import itsdangerous
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.session import get_session
from backend.models.authority import STAFF_ROLE, StaffUser

logger = logging.getLogger(__name__)

SESSION_SALT = "roadtwin-staff-session"
_hasher = PasswordHasher()
# Verifying against this when the email is unknown keeps response timing
# from revealing which emails have accounts.
_DUMMY_HASH = _hasher.hash("roadtwin-dummy-password")
_failures: dict[str, deque[float]] = {}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@functools.lru_cache(maxsize=1)
def _serializer() -> URLSafeTimedSerializer:
    secret = settings.staff_session_secret
    if not secret:
        logger.warning(
            "STAFF_SESSION_SECRET is not set -- minting an ephemeral secret; staff "
            "sessions will NOT survive a restart. Set it in backend/.env outside local dev."
        )
        secret = secrets.token_urlsafe(32)
    return URLSafeTimedSerializer(secret, salt=SESSION_SALT)


def _too_many_failures(ip: str) -> bool:
    window = _failures.get(ip)
    if not window:
        return False
    cutoff = time.monotonic() - settings.staff_login_window_seconds
    while window and window[0] < cutoff:
        window.popleft()
    return len(window) >= settings.staff_login_max_failures


def _record_failure(ip: str) -> None:
    _failures.setdefault(ip, deque()).append(time.monotonic())


def reset_login_throttle() -> None:
    _failures.clear()


async def authenticate(session: AsyncSession, email: str, password: str, ip: str) -> StaffUser:
    import sqlalchemy as sa

    if _too_many_failures(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed logins; try again later",
            headers={"Retry-After": str(settings.staff_login_window_seconds)},
        )
    user = await session.scalar(sa.select(StaffUser).where(StaffUser.email == email.strip().lower()))
    ok = verify_password(user.password_hash if user else _DUMMY_HASH, password)
    if not (user and ok and user.is_active and user.role == STAFF_ROLE):
        _record_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password")
    return user


def start_session(response: Response, user: StaffUser) -> None:
    response.set_cookie(
        key=settings.staff_session_cookie_name,
        value=_serializer().dumps({"sid": str(user.id)}),
        httponly=True,
        secure=settings.staff_session_cookie_secure,
        samesite="lax",
        max_age=settings.staff_session_max_age_seconds,
        path="/",
    )


def end_session(response: Response) -> None:
    response.delete_cookie(settings.staff_session_cookie_name, path="/")


async def require_staff(
    request: Request, session: AsyncSession = Depends(get_session)
) -> StaffUser:
    raw = request.cookies.get(settings.staff_session_cookie_name)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="staff login required")
    try:
        data = _serializer().loads(raw, max_age=settings.staff_session_max_age_seconds)
        user_id = uuid.UUID(data["sid"])
    except (itsdangerous.BadSignature, KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="staff login required")
    user = await session.get(StaffUser, user_id)
    if user is None or not user.is_active or user.role != STAFF_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="authority staff role required")
    return user
