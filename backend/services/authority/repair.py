"""Repair workflow and citizen notifications (RPWF-01, RPWF-02)."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.authority import CitizenNotification, RepairEvent, StaffUser
from backend.models.report import Report
from backend.models.road_segment import RoadSegment

STATUS_LABELS = {
    "none": "Not scheduled",
    "received": "Received",
    "in_progress": "In progress",
    "resolved": "Resolved",
}

# Allowed transitions. `resolved -> received` reopens a road whose damage
# came back.
TRANSITIONS: dict[str, set[str]] = {
    "none": {"received", "in_progress", "resolved"},
    "received": {"in_progress", "resolved"},
    "in_progress": {"resolved", "received"},
    "resolved": {"received"},
}


async def transition_repair_status(
    session: AsyncSession,
    segment: RoadSegment,
    to_status: str,
    staff: StaffUser,
    note: str | None = None,
    now: dt.datetime | None = None,
) -> tuple[RepairEvent, int]:
    """Moves the segment to `to_status`, logs it, notifies reporters. Returns (event, notified)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    from_status = segment.repair_status
    if to_status not in STATUS_LABELS:
        raise HTTPException(status_code=422, detail=f"unknown repair status {to_status!r}")
    if to_status not in TRANSITIONS.get(from_status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot move from {from_status!r} to {to_status!r}",
        )

    segment.repair_status = to_status
    if to_status == "resolved":
        # Damage seen before now stops counting toward this road's health.
        segment.last_repaired_at = now
    event = RepairEvent(
        road_segment_id=segment.id, staff_user_id=staff.id,
        from_status=from_status, to_status=to_status, note=note,
    )
    session.add(event)

    reports = (
        await session.execute(
            sa.select(Report.id, Report.submitter_identity_key).where(
                Report.segment_id == segment.id, Report.submitter_identity_key.is_not(None)
            )
        )
    ).all()
    message = (
        "Update on the road damage you reported: its repair status is now "
        f"\"{STATUS_LABELS[to_status]}\"."
    )
    for report_id, identity in reports:
        session.add(CitizenNotification(identity_key=identity, report_id=report_id, message=message))
    await session.flush()
    return event, len(reports)
