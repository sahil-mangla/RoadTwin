"""The `Prediction` entity -- append-only (SCHM-01, SCHM-02, D-08).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.5 verbatim, plus the additive `id` UUID primary key (D-05) and `method`.
`method` is the one justified addition beyond the bare spec list: FCST-01's
transparency requirement means the forecasting technique used (research
locks a two-method escalation -- ordinary least squares below roughly five
observations, damped Holt exponential smoothing above) must be recorded
per row.

FCST-03's forecast-accuracy tracking needs no extra column here: it is a
query-time join of a Prediction row against the RoadHealth row nearest
`generated_at + horizon_days`, not a stored field.

Accessed exclusively through `PredictionRepository`, which subclasses
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


class Prediction(UUIDPKMixin, Base):
    __tablename__ = "prediction"
    __table_args__ = (
        sa.Index(
            "ix_prediction_segment_generated_at",
            "road_segment_id",
            "generated_at",
        ),
    )

    road_segment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("road_segment.id"),
        nullable=False,
        index=True,
    )
    generated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    horizon_days: Mapped[int] = mapped_column(nullable=False)
    predicted_health_score: Mapped[float] = mapped_column(nullable=False)
    failure_probability: Mapped[float | None] = mapped_column(nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    method: Mapped[str] = mapped_column(nullable=False)
    # Plain-language account of how this number was produced.
    explanation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    segment: Mapped["RoadSegment"] = relationship(back_populates="predictions")
