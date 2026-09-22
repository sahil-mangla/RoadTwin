"""The `Detection` entity (SCHM-01, SCHM-03).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.2 verbatim, plus the additive `id` UUID primary key (D-05) and the
`status` column that `01-RESEARCH.md`'s RESOLUTION ADDENDUM adds beyond the
bare spec table -- resolving Open Question 3 in favour of SCHM-03's explicit
"Report and Detection" status-lifecycle requirement. `status` is bound to
the *same* `report_status_enum` instance as `Report.status`: one shared
Postgres enum type, not two (Pattern 3), so Alembic emits exactly one
`CREATE TYPE`.
"""

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPKMixin
from .enums import ReportStatus, report_status_enum

if TYPE_CHECKING:
    from .report import Report


class Detection(UUIDPKMixin, Base):
    __tablename__ = "detection"

    report_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=False, index=True
    )
    damage_type: Mapped[str] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    bbox_x1: Mapped[float] = mapped_column(nullable=False)
    bbox_y1: Mapped[float] = mapped_column(nullable=False)
    bbox_x2: Mapped[float] = mapped_column(nullable=False)
    bbox_y2: Mapped[float] = mapped_column(nullable=False)
    bbox_area_ratio: Mapped[float] = mapped_column(nullable=False)

    # Computed in Phase 3 (PERC-02) from bounding-box features -- nullable
    # here since Phase 1 defines the column, not the computation.
    severity: Mapped[str | None] = mapped_column(nullable=True)

    # Shares Report's Postgres enum type instance (not a second sa.Enum) --
    # SCHM-03's status lifecycle applies to both entities identically.
    status: Mapped[ReportStatus] = mapped_column(
        report_status_enum, default=ReportStatus.UNVERIFIED, nullable=False
    )

    report: Mapped["Report"] = relationship(back_populates="detections")
