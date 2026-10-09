"""The `RoadObservation` entity -- append-only (SCHM-01, SCHM-02, D-08).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.4 verbatim, plus the additive `id` UUID primary key (D-05). One
RoadObservation row per Detection, or per Report when a report yields no
detections (01-RESEARCH.md RESOLUTION ADDENDUM) -- hence `detection_id` is
nullable while `report_id` is not.

Accessed exclusively through `RoadObservationRepository`
(`backend/db/repository.py`), which subclasses `AppendOnlyRepository` and
defines no method that could replace or remove a row. See that module's
docstring for why this matters: the deterioration-rate (HLTH-03) and
forecast-baseline (FCST-01) formulas read this table's full history, not
just its latest row.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from .road_segment import RoadSegment


class RoadObservation(UUIDPKMixin, Base):
    __tablename__ = "road_observation"
    __table_args__ = (
        sa.Index(
            "ix_road_observation_segment_observed_at",
            "road_segment_id",
            "observed_at",
        ),
    )

    road_segment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("road_segment.id"),
        nullable=False,
        index=True,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=False
    )
    detection_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("detection.id"), nullable=True
    )
    observed_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    severity: Mapped[str | None] = mapped_column(nullable=True)
    damage_type: Mapped[str | None] = mapped_column(nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    verification_score: Mapped[float | None] = mapped_column(nullable=True)
    contribution_weight: Mapped[float | None] = mapped_column(nullable=True)

    # Phase 5 (EVID-03): the per-component breakdown behind
    # `verification_score`, so every score stays explainable after the fact.
    evidence_components: Mapped[dict | None] = mapped_column(
        postgresql.JSONB, nullable=True
    )
    # When this snapshot was written, distinct from `observed_at` (when the
    # damage was seen). A detection can have several snapshots as its
    # evidence grows; the newest `recorded_at` is its current state.
    recorded_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    segment: Mapped["RoadSegment"] = relationship(back_populates="observations")
