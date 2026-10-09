"""Enqueue side of the perception job queue (PERC-01).

Enqueueing is best-effort from the request's point of view: a Redis outage
must never fail a citizen's submission. The Report stays `pending` and can
be re-enqueued later.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from backend.core.config import settings

logger = logging.getLogger(__name__)

PERCEPTION_JOB = "run_perception"

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        # Fail fast: the submit request must not stall retrying a dead Redis.
        redis_settings.conn_retries = 0
        _pool = await create_pool(redis_settings)
    return _pool


async def enqueue_perception(report_id: uuid.UUID) -> bool:
    try:
        pool = await get_pool()
        await pool.enqueue_job(
            PERCEPTION_JOB,
            str(report_id),
            _job_id=f"perception:{report_id}",
            _defer_by=timedelta(seconds=settings.perception_enqueue_delay_seconds),
        )
        return True
    except Exception:
        logger.exception("Could not enqueue perception job for report %s", report_id)
        return False


SEGMENTATION_JOB = "run_segmentation_job"


async def enqueue_segmentation() -> bool:
    """Debounced: a fixed job id collapses a burst of triggers into one run."""
    try:
        pool = await get_pool()
        await pool.enqueue_job(
            SEGMENTATION_JOB,
            _job_id="segmentation",
            _defer_by=timedelta(seconds=settings.segmentation_defer_seconds),
        )
        return True
    except Exception:
        logger.exception("Could not enqueue segmentation job")
        return False
