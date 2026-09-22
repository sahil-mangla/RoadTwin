"""The `RoadHealth` entity -- append-only (SCHM-01, SCHM-02, D-08).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.5 verbatim, plus the additive `id` UUID primary key (D-05). No column
for a stored health-band label: reference spec §6 defines the
Excellent/Good/Poor/Critical/Severely-degraded reading of `health_score` as
a display-time interpretation, computed on read in Phase 6, never
persisted here.

Accessed exclusively through `RoadHealthRepository`, which subclasses
`AppendOnlyRepository` and defines no replace/remove method -- see
`backend/db/repository.py`.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from .road_segment import RoadSegment


class RoadHealth(UUIDPKMixin, Base):
    __tablename__ = "road_health"
    __table_args__ = (
        sa.Index(
            "ix_road_health_segment_measured_at",
            "road_segment_id",
            "measured_at",
        ),
    )

    road_segment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("road_segment.id"),
        nullable=False,
        index=True,
    )
    measured_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    health_score: Mapped[float] = mapped_column(nullable=False)
    severity_burden: Mapped[float | None] = mapped_column(nullable=True)
    damage_density: Mapped[float | None] = mapped_column(nullable=True)
    evidence_score: Mapped[float | None] = mapped_column(nullable=True)
    deterioration_rate: Mapped[float | None] = mapped_column(nullable=True)
    risk_score: Mapped[float | None] = mapped_column(nullable=True)

    segment: Mapped["RoadSegment"] = relationship(back_populates="health_records")
