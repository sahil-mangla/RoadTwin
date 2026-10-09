"""A citizen's own in-app notifications (RPWF-02), keyed by their device cookie."""

import datetime as dt
import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_session
from backend.models.authority import CitizenNotification
from backend.services.ingestion.identity import get_device_identity

router = APIRouter(prefix="/api/me", tags=["citizen"])


class NotificationRead(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID
    message: str
    created_at: dt.datetime
    read: bool


@router.get("/notifications", response_model=list[NotificationRead])
async def my_notifications(
    session: AsyncSession = Depends(get_session),
    device_id: str = Depends(get_device_identity),
) -> list[NotificationRead]:
    rows = (
        await session.scalars(
            sa.select(CitizenNotification)
            .where(CitizenNotification.identity_key == device_id)
            .order_by(CitizenNotification.created_at.desc())
            .limit(50)
        )
    ).all()
    return [
        NotificationRead(id=n.id, report_id=n.report_id, message=n.message,
                         created_at=n.created_at, read=n.read_at is not None)
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    device_id: str = Depends(get_device_identity),
) -> None:
    note = await session.get(CitizenNotification, notification_id)
    # Someone else's notification looks exactly like a missing one.
    if note is None or note.identity_key != device_id:
        raise HTTPException(status_code=404, detail="notification not found")
    if note.read_at is None:
        note.read_at = dt.datetime.now(dt.timezone.utc)
