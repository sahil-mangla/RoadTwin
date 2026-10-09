"""The `Report` entity (SCHM-01, first of seven; SCHM-03; SCHM-04).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.1 verbatim, plus the additive fields D-05 (UUID PK), D-07 (GPS accuracy)
and CONTEXT.md's Claude's-Discretion geometry column authorise. Phase 2
resolved citizen identity (INGT-02) as an opaque signed-cookie device
identifier (D-01) -- deliberately NOT a foreign key to any user table,
because no user table exists and D-02 rules out building one.
"""

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from geoalchemy2 import Geometry, WKBElement
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampedMixin, UUIDPKMixin
from .enums import ReportStatus, report_status_enum

if TYPE_CHECKING:
    from .detection import Detection

# NOTE on the `detections` relationship below: 01-01-PLAN.md's Task 3
# action described adding it under a `TYPE_CHECKING` guard immediately,
# but SQLAlchemy resolves relationship() string class references at
# *mapper configuration* time (triggered by the first instantiation or
# query against ANY mapped class in this registry), not at *import* time
# -- a `TYPE_CHECKING` guard only protects the import statement above, so
# a relationship pointing at "Detection" before `backend/models/detection.py`
# existed would have raised `InvalidRequestError` on the very first
# `Report()` call. 01-01-SUMMARY.md documented this as a deferred
# deviation; this plan (04) is where `Detection` now exists, so both
# sides of `back_populates` can resolve together.


class Report(UUIDPKMixin, TimestampedMixin, Base):
    __tablename__ = "report"

    # Nullable because image upload is INGT-01/INGT-04 (Phase 2); Phase 2
    # owns this column's population and decides its final nullability.
    # Narrowed to String(256) here -- the length half of D-08 / 01-REVIEW.md
    # WR-02 that the Pydantic layer (ReportCreate.image_path) also enforces.
    image_path: Mapped[str | None] = mapped_column(sa.String(256), nullable=True)

    # Opaque signed-cookie device identifier (D-01, INGT-02). Nullable
    # because Phase 1 rows and the skeleton route create Reports with no
    # identity; the citizen route (backend/routes/reports.py) always
    # populates it. Not a verified person -- clearable, shareable, and not
    # bound to any credential -- so it supports rate limiting (Phase 2
    # Plan 04) and one-corroboration-per-report (Phase 5 EVID-04), not
    # non-repudiation.
    submitter_identity_key: Mapped[str | None] = mapped_column(
        sa.String(64), nullable=True, index=True
    )

    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)

    # Horizontal accuracy radius in meters, matching the browser Geolocation
    # API's `coords.accuracy` semantics. Nullable only because a manual
    # map-pin submission has no device-reported accuracy (D-07, SCHM-04).
    gps_accuracy_meters: Mapped[float | None] = mapped_column(nullable=True)

    # Additive spatial column (Claude's Discretion resolution) so Phase 4's
    # spatial-clustering queries need no later migration.
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )

    # Client-reported observation time -- distinct from the inherited
    # `created_at` (server insert time). Both exist; do not collapse them.
    timestamp: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )

    source: Mapped[str] = mapped_column(nullable=False, default="citizen")
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    community_upvotes: Mapped[int] = mapped_column(nullable=False, default=0)

    # Computed in Phase 5 (EVID-01) -- nullable until then.
    verification_score: Mapped[float | None] = mapped_column(nullable=True)

    status: Mapped[ReportStatus] = mapped_column(
        report_status_enum, default=ReportStatus.UNVERIFIED, nullable=False
    )

    # Background-inference lifecycle (PERC-01), separate from the
    # verification `status` above: pending -> processing -> done | failed.
    perception_status: Mapped[str] = mapped_column(
        sa.String(16), default="pending", server_default="pending", nullable=False
    )

    # Phase 4 (SPAT-01/02): set by the segmentation job. `duplicate_of_id`
    # points at the canonical report for the same physical damage (NULL on
    # the canonical itself); `segment_id` is the RoadSegment the report's
    # canonical point was aggregated into.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("report.id"), nullable=True, index=True
    )
    segment_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("road_segment.id"), nullable=True, index=True
    )

    detections: Mapped[list["Detection"]] = relationship(
        back_populates="report", lazy="selectin"
    )

    def __init__(self, **kwargs):
        # `mapped_column(default=...)` is an INSERT-time (flush-time)
        # default, not a construction-time one -- so without this override
        # `Report(...).status` would read back `None` until the object is
        # flushed. SCHM-03 and this plan's own contract test require the
        # in-memory default to be observable immediately after
        # construction, before any DB round-trip, so it is set explicitly
        # here when the caller does not supply one.
        kwargs.setdefault("status", ReportStatus.UNVERIFIED)
        kwargs.setdefault("source", "citizen")
        kwargs.setdefault("community_upvotes", 0)
        super().__init__(**kwargs)
