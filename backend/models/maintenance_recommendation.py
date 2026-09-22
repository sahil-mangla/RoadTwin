"""The `MaintenanceRecommendation` entity (SCHM-01).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.6 verbatim, plus the additive `id` UUID primary key (D-05). No
repair-workflow state column of any kind is added here -- RPWF-01 belongs
to Phase 7, and which entity owns that state is itself a Phase 7 design
question this phase must not pre-empt.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from .road_segment import RoadSegment


class MaintenanceRecommendation(UUIDPKMixin, Base):
    __tablename__ = "maintenance_recommendation"

    road_segment_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True),
        sa.ForeignKey("road_segment.id"),
        nullable=False,
        index=True,
    )
    priority_score: Mapped[float] = mapped_column(nullable=False)
    urgency: Mapped[str] = mapped_column(nullable=False)
    recommended_action: Mapped[str] = mapped_column(nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # PRIO-02 requires an explanation alongside every score -- required,
    # not optional.
    explanation: Mapped[str] = mapped_column(sa.Text, nullable=False)

    segment: Mapped["RoadSegment"] = relationship(back_populates="recommendations")
