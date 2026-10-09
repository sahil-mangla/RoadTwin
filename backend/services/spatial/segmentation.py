"""The clustering job: reports -> duplicate groups -> road segments (SPAT-01..03).

Re-running is safe and idempotent: duplicate links are recomputed from
scratch each run (oldest report stays canonical), and segment identities
are reconciled onto existing RoadSegment rows instead of minted anew.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import RoadSegmentRepository
from backend.models.detection import Detection
from backend.models.enums import ReportStatus
from backend.models.geo import make_linestring
from backend.models.report import Report
from backend.models.road_segment import RoadSegment
from backend.services.spatial.clustering import GeoItem, assign_duplicates, group_items
from backend.services.spatial.geo import haversine_m, principal_axis_endpoints
from backend.services.spatial.reconcile import ExistingSegment, reconcile

logger = logging.getLogger(__name__)

# Arbitrary constant; serialises overlapping runs across worker processes.
_ADVISORY_LOCK_KEY = 0x524F4144  # "ROAD"


@dataclass(frozen=True)
class SegmentationSummary:
    reports: int
    canonical_reports: int
    duplicates: int
    segments_total: int
    segments_created: int


def _new_segment_identifier() -> str:
    return f"SEG-{uuid.uuid4().hex[:12].upper()}"


async def run_segmentation(session: AsyncSession) -> SegmentationSummary:
    await session.execute(sa.select(sa.func.pg_advisory_xact_lock(_ADVISORY_LOCK_KEY)))

    # Only reports where inference finished and found damage describe
    # damaged road; rejected reports never count.
    has_detection = sa.exists().where(Detection.report_id == Report.id)
    rows = (
        await session.execute(
            sa.select(Report).where(
                Report.perception_status == "done",
                Report.status != ReportStatus.REJECTED,
                has_detection,
            )
        )
    ).scalars().all()

    items = [
        GeoItem(r.id, (r.latitude, r.longitude), (r.created_at, str(r.id))) for r in rows
    ]
    by_id = {r.id: r for r in rows}

    # --- SPAT-01: near-duplicate links -------------------------------
    canonical_of = assign_duplicates(items, settings.duplicate_radius_meters)
    for report in rows:
        canonical_id = canonical_of[report.id]
        report.duplicate_of_id = None if canonical_id == report.id else canonical_id

    canonical_items = [i for i in items if canonical_of[i.id] == i.id]

    # --- SPAT-02: aggregate canonical points into segments ------------
    groups = group_items(canonical_items, settings.segment_cluster_radius_meters)
    clusters = [
        [(i.id, i.point, by_id[i.id].segment_id) for i in group] for group in groups
    ]

    existing = (await session.execute(sa.select(RoadSegment))).scalars().all()
    existing_by_id = {s.id: s for s in existing}
    matches = reconcile(
        clusters,
        [
            ExistingSegment(s.id, (s.start_lat, s.start_lng), (s.end_lat, s.end_lng))
            for s in existing
        ],
        settings.segment_reconcile_distance_meters,
    )

    # --- SPAT-03: write onto stable identities ------------------------
    segments = RoadSegmentRepository(session)
    created = 0
    segment_of_canonical: dict[uuid.UUID, uuid.UUID] = {}
    for group, matched_id in zip(groups, matches):
        start, end = principal_axis_endpoints([i.point for i in group])
        length = haversine_m(start, end)
        if matched_id is None:
            segment = await segments.create(
                segment_identifier=_new_segment_identifier(),
                start_lat=start[0],
                start_lng=start[1],
                end_lat=end[0],
                end_lng=end[1],
                length_meters=length,
            )
            created += 1
        else:
            segment = existing_by_id[matched_id]
            await segments.update(
                segment,
                start_lat=start[0],
                start_lng=start[1],
                end_lat=end[0],
                end_lng=end[1],
                length_meters=length,
                geometry=make_linestring(start[0], start[1], end[0], end[1]),
            )
        for item in group:
            segment_of_canonical[item.id] = segment.id

    for report in rows:
        report.segment_id = segment_of_canonical[canonical_of[report.id]]
    await session.flush()

    summary = SegmentationSummary(
        reports=len(rows),
        canonical_reports=len(canonical_items),
        duplicates=len(rows) - len(canonical_items),
        segments_total=len(existing) + created,
        segments_created=created,
    )
    logger.info("segmentation finished: %s", summary)
    return summary
