"""Dual-key rate limiting and GPS cooldown (INGT-03, D-03..D-06).

D-03: state lives in Postgres, not Redis -- Redis is reserved for Phase 3's
inference queue. D-04: the limiter is keyed on BOTH the device identity and
the client IP; whichever breaches first governs the rejection. D-05: an
identity-agnostic spatial cooldown additionally guards against rapid
repeated submissions at one location. D-06: every rejection is an
explicit 429 with `Retry-After`, never a silent drop.

This is a best-effort anti-spam control with a known bypass (clearing
cookies while rotating IP), NOT a security boundary -- CONTEXT.md places
full bot resistance out of v1 scope. 02-RESEARCH.md found no
Postgres-native rate-limiting library fitting these constraints, which is
why this one module is hand-rolled; it must stay small rather than growing
into a general-purpose framework.

Accepted TOCTOU residual risk: the COUNT query and the SubmissionAttempt
insert are not a single atomic operation. Two concurrent requests from the
same identity or IP can both pass the COUNT check before either commits,
so the effective limit can be exceeded by a small margin under true
concurrency. This is accepted for a v1 best-effort control (CONTEXT.md's
explicit non-goal of full bot resistance); the shared request transaction
boundary (not an advisory lock) is the mitigation actually implemented. A
Postgres advisory lock keyed on `identity_key` is the known upgrade path
if exactness is ever required.
"""

import datetime as dt
from dataclasses import dataclass

import sqlalchemy as sa
from fastapi import HTTPException, status
from geoalchemy2 import Geography
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import SubmissionAttemptRepository
from backend.models.rate_limit import SubmissionAttempt
from backend.models.report import Report
from backend.models.geo import make_point


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str | None
    retry_after_seconds: int | None


async def count_recent_attempts(
    session: AsyncSession, *, column, value, window_seconds: int
) -> int:
    """Rolling-window COUNT, inclusive of `window_start` (non-strict `>=`).

    A rolling-window COUNT is preferred over a fixed-window counter
    increment: a fixed window admits a boundary burst of up to twice the
    limit across two adjacent windows.
    """
    window_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=window_seconds)
    stmt = sa.select(sa.func.count()).select_from(SubmissionAttempt).where(
        column == value,
        # Inclusive window boundary -- matches the ST_DWithin distance
        # comparison's own inclusive semantics below, so a submission
        # sitting exactly on one boundary is not treated differently from
        # one sitting exactly on the other.
        SubmissionAttempt.created_at >= window_start,
    )
    result = await session.scalar(stmt)
    return result or 0


async def has_recent_nearby_report(
    session: AsyncSession, *, latitude: float, longitude: float
) -> bool:
    """True only for a prior report within `gps_cooldown_meters` metres and seconds."""
    window_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        seconds=settings.gps_cooldown_seconds
    )
    query_point = make_point(latitude, longitude)

    # Both `ST_DWithin` operands MUST be cast to `Geography` -- this is the
    # single most important line in this module. `ST_DWithin` on a raw
    # SRID-4326 *geometry* measures its third argument in DEGREES, so
    # passing `gps_cooldown_meters` (15) unwrapped would mean roughly
    # 1600 km and would reject essentially every submission in the
    # country. Casting both operands to `geography` makes the threshold
    # metres. (02-RESEARCH.md Pattern 2's `sa.cast(..., sa.String)` was
    # illustrative only and must not be copied literally.)
    stmt = sa.select(sa.func.count()).select_from(Report).where(
        Report.created_at >= window_start,
        sa.func.ST_DWithin(
            sa.cast(Report.location, Geography),
            sa.cast(query_point, Geography),
            settings.gps_cooldown_meters,
        ),
    )
    count = await session.scalar(stmt)
    return (count or 0) > 0


async def evaluate_rate_limits(
    session: AsyncSession,
    *,
    identity_key: str,
    ip_address: str,
    latitude: float | None,
    longitude: float | None,
) -> RateLimitDecision:
    """Checks identity, then IP, then the spatial cooldown -- first breach governs (D-04)."""
    identity_count = await count_recent_attempts(
        session,
        column=SubmissionAttempt.identity_key,
        value=identity_key,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if identity_count >= settings.identity_rate_limit_per_hour:
        return RateLimitDecision(
            allowed=False,
            reason="too many recent submissions from this device -- please wait before submitting again",
            retry_after_seconds=settings.rate_limit_window_seconds,
        )

    ip_count = await count_recent_attempts(
        session,
        column=SubmissionAttempt.ip_address,
        value=ip_address,
        window_seconds=settings.rate_limit_window_seconds,
    )
    if ip_count >= settings.ip_rate_limit_per_hour:
        return RateLimitDecision(
            allowed=False,
            reason="too many recent submissions from this network -- please wait before submitting again",
            retry_after_seconds=settings.rate_limit_window_seconds,
        )

    if latitude is not None and longitude is not None:
        if await has_recent_nearby_report(session, latitude=latitude, longitude=longitude):
            return RateLimitDecision(
                allowed=False,
                reason="a report near this location was recently submitted -- please wait before submitting another",
                retry_after_seconds=settings.gps_cooldown_seconds,
            )

    return RateLimitDecision(allowed=True, reason=None, retry_after_seconds=None)


async def enforce_rate_limits(
    session: AsyncSession,
    *,
    identity_key: str,
    ip_address: str,
    latitude: float | None,
    longitude: float | None,
) -> None:
    """Raises 429 with `Retry-After` on any breach; never a silent 200/201 (D-06)."""
    decision = await evaluate_rate_limits(
        session,
        identity_key=identity_key,
        ip_address=ip_address,
        latitude=latitude,
        longitude=longitude,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=decision.reason,
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


async def record_submission_attempt(
    session: AsyncSession, *, identity_key: str, ip_address: str
) -> None:
    """Creates one attempt row. Does not commit -- the caller's transaction owns that."""
    await SubmissionAttemptRepository(session).create(
        identity_key=identity_key, ip_address=ip_address
    )


async def prune_old_attempts(session: AsyncSession) -> int:
    """Deletes `submission_attempt` rows older than the retention window.

    Scoped ONLY to `submission_attempt` -- this table is operational
    telemetry (see backend/models/rate_limit.py's docstring), never any
    other application table, and never an SCHM-02 append-only evidence
    entity. Not invoked from the request path; a scheduler is Phase 3's
    concern.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
        days=settings.submission_attempt_retention_days
    )
    stmt = sa.delete(SubmissionAttempt).where(SubmissionAttempt.created_at < cutoff)
    result = await session.execute(stmt)
    return result.rowcount or 0
