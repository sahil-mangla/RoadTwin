"""arq worker: runs YOLOv8 inference off the request path (PERC-01).

Run with `arq backend.worker.WorkerSettings` from the repository root.
"""

import asyncio
import logging
import uuid

from arq import Retry, cron, func
from arq.connections import RedisSettings

from backend.core.config import settings
from backend.db.session import async_session_factory
from backend.services.ingestion.upload import get_report_image_bytes
from backend.services.perception.detector import load_detector
from backend.services.perception.pipeline import ReportNotFound, process_report
from backend.services.perception.queue import enqueue_segmentation
from backend.services.intelligence.assessment import assess_segments
from backend.services.intelligence.observations import record_observations
from backend.services.maintenance.prioritize import prioritize_segments
from backend.services.spatial.segmentation import run_segmentation

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    # arq only configures its own logger; without this our INFO lines
    # (per-component evidence contributions, segmentation summaries) are
    # dropped.
    app_logger = logging.getLogger("backend")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s: %(name)s: %(message)s", "%H:%M:%S"))
        app_logger.addHandler(handler)
    ctx["detector"] = load_detector()


async def run_perception(ctx: dict, report_id: str) -> int:
    rid = uuid.UUID(report_id)
    try:
        async with async_session_factory() as session:
            try:
                image_path = await _image_path(session, rid)
                image_bytes = await asyncio.to_thread(get_report_image_bytes, image_path)
                count = await process_report(session, rid, image_bytes, ctx["detector"])
                await session.commit()
                if count:
                    await enqueue_segmentation()
                return count
            except Exception:
                await session.rollback()
                raise
    except ReportNotFound:
        # The submitting transaction may not have committed yet.
        raise Retry(defer=ctx["job_try"] * 2)
    except Exception:
        if ctx["job_try"] >= settings.perception_job_max_tries:
            await _mark_failed(rid)
        raise


async def run_segmentation_job(ctx: dict) -> dict:
    async with async_session_factory() as session:
        segmentation = await run_segmentation(session)
        observations = await record_observations(session)
        assessment = await assess_segments(session)
        priority = await prioritize_segments(session)
        await session.commit()
    return {
        **segmentation.__dict__,
        **observations.__dict__,
        **assessment.__dict__,
        **priority.__dict__,
    }


async def _image_path(session, report_id: uuid.UUID) -> str:
    from backend.db.repository import ReportRepository

    report = await ReportRepository(session).get(report_id)
    if report is None:
        raise ReportNotFound(str(report_id))
    if report.image_path is None:
        raise ValueError(f"report {report_id} has no stored image")
    return report.image_path


async def _mark_failed(report_id: uuid.UUID) -> None:
    from backend.db.repository import ReportRepository

    async with async_session_factory() as session:
        repo = ReportRepository(session)
        report = await repo.get(report_id)
        if report is not None:
            await repo.update(report, perception_status="failed")
            await session.commit()


class WorkerSettings:
    # keep_result=0: arq refuses to enqueue a job id that still has a stored
    # result, which would silently swallow every debounced trigger for an
    # hour after the first run. Without a stored result the fixed id only
    # dedupes a job that is still queued or running.
    functions = [run_perception, func(run_segmentation_job, keep_result=0)]
    # Safety net in case a trigger was lost (e.g. Redis restart).
    cron_jobs = [cron(run_segmentation_job, minute={0, 15, 30, 45}, unique=True, keep_result=0)]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = settings.perception_job_max_tries
    # Inference is CPU-bound and the model instance is shared: one job at
    # a time keeps a single YOLO instance thread-safe.
    max_jobs = 1
    job_timeout = 120
