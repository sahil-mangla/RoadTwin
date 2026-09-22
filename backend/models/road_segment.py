"""The `RoadSegment` entity -- the primary intelligence entity in RoadTwin.

Field list matches `.planning/reference/RoadTwin-Architecture-Input-Spec.md`
§4.3 verbatim, plus the additive `id` UUID primary key (D-05) and a
`Geometry(LINESTRING, 4326)` column derived from the four endpoint floats
(CONTEXT.md's Claude's-Discretion geometry resolution, consistent with
Report's point column) -- never stored independently of the endpoints.
"""

import datetime as dt
from typing import TYPE_CHECKING

import sqlalchemy as sa
from geoalchemy2 import Geometry, WKBElement
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from .maintenance_recommendation import MaintenanceRecommendation
    from .prediction import Prediction
    from .road_health import RoadHealth
    from .road_observation import RoadObservation


class RoadSegment(UUIDPKMixin, Base):
    """The road segment aggregates observations and holds current state.

    `current_health_score`, `current_risk_score`, `deterioration_rate` and
    `last_observed_at` are Phase 5-7 outputs (evidence fusion / health
    scoring / deterioration). Phase 1 only defines these columns as
    nullable placeholders -- populating them is explicitly out of this
    phase's scope.
    """

    __tablename__ = "road_segment"

    # Stable identity SPAT-03 reconciles onto across re-clustering runs
    # (Phase 4).
    segment_identifier: Mapped[str] = mapped_column(nullable=False, unique=True)

    start_lat: Mapped[float] = mapped_column(nullable=False)
    start_lng: Mapped[float] = mapped_column(nullable=False)
    end_lat: Mapped[float] = mapped_column(nullable=False)
    end_lng: Mapped[float] = mapped_column(nullable=False)

    # Derived from the four endpoint floats above via `make_linestring` --
    # never stored independently of them (see RoadSegmentRepository.create).
    geometry: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=True),
        nullable=False,
    )

    road_name: Mapped[str | None] = mapped_column(nullable=True)
    road_type: Mapped[str | None] = mapped_column(nullable=True)
    length_meters: Mapped[float | None] = mapped_column(nullable=True)

    # Phase 5-7 outputs -- see class docstring.
    current_health_score: Mapped[float | None] = mapped_column(nullable=True)
    current_risk_score: Mapped[float | None] = mapped_column(nullable=True)
    deterioration_rate: Mapped[float | None] = mapped_column(nullable=True)
    last_observed_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    observations: Mapped[list["RoadObservation"]] = relationship(
        back_populates="segment", lazy="selectin"
    )
    health_records: Mapped[list["RoadHealth"]] = relationship(
        back_populates="segment", lazy="selectin"
    )
    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="segment", lazy="selectin"
    )
    recommendations: Mapped[list["MaintenanceRecommendation"]] = relationship(
        back_populates="segment", lazy="selectin"
    )
