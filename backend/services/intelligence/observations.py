"""Turns segmented reports into scored, append-only RoadObservation history (EVID-01..04, HLTH-01).

Runs right after segmentation inside the same transaction. For every
detection on an eligible report it:

1. scores the detection from five signals (see `evidence.py`), where the
   group is the damage's canonical report plus its near-duplicates and
   "independent" means one report per distinct identity -- one person
   re-reporting, or voting for, their own damage cannot inflate it;
2. appends a RoadObservation snapshot when the detection is new to its
   segment's history or its evidence moved materially (rows are never
   updated, so each segment keeps a real longitudinal record);
3. refreshes the mutable summary on Report (verification_score,
   community_upvotes) and advances its status lifecycle.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import RoadObservationRepository
from backend.models.corroboration import ReportCorroboration
from backend.models.detection import Detection
from backend.models.enums import ReportStatus
from backend.models.report import Report
from backend.models.road_observation import RoadObservation
from backend.services.intelligence.evidence import (
    EvidenceInputs,
    IndependentReport,
    compute_evidence,
    format_log,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservationSummary:
    detections_scored: int
    observations_recorded: int
    reports_confirmed: int
    reports_corroborated: int


def _identity_of(report: Report) -> str:
    # A report with no identity (legacy / skeleton rows) is its own reporter.
    return report.submitter_identity_key or f"anonymous:{report.id}"


async def record_observations(session: AsyncSession) -> ObservationSummary:
    has_detection = sa.exists().where(Detection.report_id == Report.id)
    reports = (
        await session.execute(
            sa.select(Report).where(
                Report.perception_status == "done",
                Report.status != ReportStatus.REJECTED,
                Report.segment_id.is_not(None),
                has_detection,
            )
        )
    ).scalars().all()
    if not reports:
        return ObservationSummary(0, 0, 0, 0)

    report_ids = [r.id for r in reports]
    votes_by_report: dict[uuid.UUID, set[str]] = {}
    for report_id, identity in (
        await session.execute(
            sa.select(ReportCorroboration.report_id, ReportCorroboration.identity_key).where(
                ReportCorroboration.report_id.in_(report_ids)
            )
        )
    ).all():
        votes_by_report.setdefault(report_id, set()).add(identity)

    groups: dict[uuid.UUID, list[Report]] = {}
    for r in reports:
        groups.setdefault(r.duplicate_of_id or r.id, []).append(r)

    detection_ids = [d.id for r in reports for d in r.detections]
    latest: dict[uuid.UUID, RoadObservation] = {}
    for obs in (
        await session.execute(
            sa.select(RoadObservation)
            .where(RoadObservation.detection_id.in_(detection_ids))
            .order_by(RoadObservation.recorded_at)
        )
    ).scalars():
        latest[obs.detection_id] = obs  # ascending, so the last one wins

    repo = RoadObservationRepository(session)
    scored = recorded = confirmed = corroborated = 0

    for members in groups.values():
        # One report per identity (their earliest) counts as independent.
        earliest: dict[str, Report] = {}
        for r in sorted(members, key=lambda r: (r.timestamp, str(r.id))):
            earliest.setdefault(_identity_of(r), r)
        reporters = [
            IndependentReport(point=(r.latitude, r.longitude), observed_at=r.timestamp)
            for r in earliest.values()
        ]
        submitters = set(earliest)
        voters = set().union(*(votes_by_report.get(r.id, set()) for r in members)) - submitters

        for report in members:
            best = 0.0
            for det in report.detections:
                result = compute_evidence(
                    EvidenceInputs(det.confidence, reporters, len(voters)), settings
                )
                scored += 1
                best = max(best, result.score)
                logger.info(format_log(f"detection={det.id}", result))

                prior = latest.get(det.id)
                if (
                    prior is None
                    or prior.road_segment_id != report.segment_id
                    or abs((prior.verification_score or 0.0) - result.score)
                    >= settings.evidence_resnapshot_delta
                ):
                    snapshot = await repo.create(
                        road_segment_id=report.segment_id,
                        report_id=report.id,
                        detection_id=det.id,
                        observed_at=report.timestamp,
                        severity=det.severity,
                        damage_type=det.damage_type,
                        confidence=det.confidence,
                        verification_score=result.score,
                        evidence_components=result.as_record(),
                        recorded_at=dt.datetime.now(dt.timezone.utc),
                    )
                    latest[det.id] = snapshot
                    recorded += 1

            report.verification_score = best
            report.community_upvotes = len(votes_by_report.get(report.id, ()))

            if report.status in (ReportStatus.UNVERIFIED, ReportStatus.CORROBORATED):
                if best >= settings.evidence_confirmed_threshold:
                    report.status = ReportStatus.EVIDENCE_CONFIRMED
                    confirmed += 1
                elif report.status == ReportStatus.UNVERIFIED and (
                    len(reporters) >= settings.corroborated_min_independent_reporters
                    or len(voters) >= settings.corroborated_min_votes
                ):
                    report.status = ReportStatus.CORROBORATED
                    corroborated += 1

    await session.flush()
    return ObservationSummary(scored, recorded, confirmed, corroborated)
