"""Turns one Report's stored image into persisted Detection rows (PERC-02/03)."""

from __future__ import annotations

import asyncio
import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import DetectionRepository, ReportRepository
from backend.models.detection import Detection
from backend.core.config import settings
from backend.services.perception.detector import Detector
from backend.services.perception.postprocess import merge_overlapping
from backend.services.perception.severity import (
    bbox_area_ratio,
    canonical_damage_type,
    derive_severity,
)

logger = logging.getLogger(__name__)


class ReportNotFound(Exception):
    """The Report row is not visible (yet) -- the job should be retried."""


async def process_report(
    session: AsyncSession, report_id: uuid.UUID, image_bytes: bytes, detector: Detector
) -> int:
    """Runs `detector` and persists one Detection per defect. Returns the count.

    Idempotent: a retried job replaces any Detections from a half-finished
    earlier attempt instead of duplicating them, so every image yields
    exactly its detections no matter how many times the job runs.
    """
    reports = ReportRepository(session)
    report = await reports.get(report_id)
    if report is None:
        raise ReportNotFound(str(report_id))

    await reports.update(report, perception_status="processing")
    # Inference is CPU-bound; keep it off the event loop.
    result = await asyncio.to_thread(detector.detect, image_bytes)

    await session.execute(sa.delete(Detection).where(Detection.report_id == report_id))
    detections = DetectionRepository(session)
    distinct = merge_overlapping(
        result.detections,
        iou_threshold=settings.detection_merge_iou,
        containment_threshold=settings.detection_merge_containment,
    )
    for raw in distinct:
        ratio = bbox_area_ratio(raw.x1, raw.y1, raw.x2, raw.y2, result.width, result.height)
        damage_type = canonical_damage_type(raw.damage_type)
        await detections.create(
            report_id=report_id,
            damage_type=damage_type,
            confidence=raw.confidence,
            bbox_x1=raw.x1,
            bbox_y1=raw.y1,
            bbox_x2=raw.x2,
            bbox_y2=raw.y2,
            bbox_area_ratio=ratio,
            severity=derive_severity(damage_type, ratio),
        )

    await reports.update(report, perception_status="done")
    return len(distinct)
