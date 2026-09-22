"""The `Report` entity (SCHM-01, first of seven; SCHM-03; SCHM-04).

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.1 verbatim, plus the additive fields D-05 (UUID PK), D-07 (GPS accuracy)
and CONTEXT.md's Claude's-Discretion geometry column authorise. No
citizen-identity foreign key is added here -- that decision belongs to
Phase 2 (INGT-02), so Phase 1 does not pre-empt it.
"""

import datetime as dt

import sqlalchemy as sa
from geoalchemy2 import Geometry, WKBElement
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampedMixin, UUIDPKMixin
from .enums import ReportStatus, report_status_enum

# NOTE: no `detections: Mapped[list["Detection"]] = relationship(...)` here
# yet, even though 01-01-PLAN.md's Task 3 action describes adding one now
# under `if TYPE_CHECKING:`. SQLAlchemy resolves relationship() string
# class references at *mapper configuration* time (triggered by the first
# instantiation or query against ANY mapped class in this registry), not
# at *import* time -- a `TYPE_CHECKING` guard only protects the import, so
# a relationship pointing at "Detection" before `backend/models/detection.py`
# exists raises `InvalidRequestError` on the very first `Report()` call,
# breaking every test in this plan. Deviation (Rule 1 - bug): the
# relationship is deferred to Plan 04, added alongside `Detection` itself,
# where both sides of `back_populates` can resolve together.


class Report(UUIDPKMixin, TimestampedMixin, Base):
    __tablename__ = "report"

    # Nullable because image upload is INGT-01/INGT-04 (Phase 2); Phase 2
    # owns this column's population and decides its final nullability.
    image_path: Mapped[str | None] = mapped_column(nullable=True)

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
