"""Repository layer -- the structural enforcement point for D-08/SCHM-02.

Every query is built with SQLAlchemy `select()` constructs and bound
parameters; no value is ever interpolated into query text (threat T-01-03).
"""

from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.corroboration import ReportCorroboration
from backend.models.detection import Detection
from backend.models.geo import make_linestring, make_point
from backend.models.maintenance_recommendation import MaintenanceRecommendation
from backend.models.prediction import Prediction
from backend.models.rate_limit import SubmissionAttempt
from backend.models.report import Report
from backend.models.road_health import RoadHealth
from backend.models.road_observation import RoadObservation
from backend.models.road_segment import RoadSegment

T = TypeVar("T")


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> T:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def get(self, id) -> T | None:
        stmt = sa.select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        limit: int = 50,
        order_by: str | None = None,
        descending: bool = False,
        **filters,
    ) -> list[T]:
        stmt = sa.select(self.model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
        if order_by is not None:
            column = getattr(self.model, order_by)
            stmt = stmt.order_by(column.desc() if descending else column.asc())
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MutableRepository(BaseRepository[T]):
    """Adds `update()` -- used for Report, Detection, RoadSegment, MaintenanceRecommendation."""

    async def update(self, obj: T, **changes) -> T:
        for field, value in changes.items():
            setattr(obj, field, value)
        await self.session.flush()
        return obj


class AppendOnlyRepository(BaseRepository[T]):
    """Adds nothing beyond `create`/`get`/`list`.

    The absence of any mutating method here is the enforcement mechanism
    for SCHM-02/D-08: RoadObservation, RoadHealth, and Prediction rows may
    only ever be created, never replaced or removed, through this data
    access path. Adding an `update` or `delete` method to this class -- or
    to any of its subclasses -- silently breaks the longitudinal history
    the deterioration-rate and forecast formulas require. Do not add one.
    """


class ReportRepository(MutableRepository[Report]):
    model = Report

    async def create(self, **kwargs) -> Report:
        if "location" not in kwargs:
            kwargs = {
                **kwargs,
                "location": make_point(kwargs["latitude"], kwargs["longitude"]),
            }
        return await super().create(**kwargs)


class SubmissionAttemptRepository(BaseRepository[SubmissionAttempt]):
    """Parent is `BaseRepository`, not `MutableRepository`.

    02-RESEARCH.md's chosen design is append-and-count: one row per
    accepted submission attempt, never updated after insert. No `update()`
    is needed, and inheriting one would widen the surface for no reason.
    """

    model = SubmissionAttempt


class ReportCorroborationRepository(BaseRepository[ReportCorroboration]):
    """Append-only votes; the unique constraint enforces one per identity per report."""

    model = ReportCorroboration


class DetectionRepository(MutableRepository[Detection]):
    model = Detection


class RoadSegmentRepository(MutableRepository[RoadSegment]):
    model = RoadSegment

    async def create(self, **kwargs) -> RoadSegment:
        if "geometry" not in kwargs:
            kwargs = {
                **kwargs,
                "geometry": make_linestring(
                    kwargs["start_lat"],
                    kwargs["start_lng"],
                    kwargs["end_lat"],
                    kwargs["end_lng"],
                ),
            }
        return await super().create(**kwargs)


class MaintenanceRecommendationRepository(MutableRepository[MaintenanceRecommendation]):
    model = MaintenanceRecommendation


class RoadObservationRepository(AppendOnlyRepository[RoadObservation]):
    """Adds nothing beyond what `AppendOnlyRepository` provides -- deliberately (SCHM-02, D-08).

    RoadObservation rows are the raw longitudinal evidence stream Phase 5's
    evidence fusion produces and Phase 6's health-score/deterioration-rate
    formulas read in full, from the beginning of a segment's history. Any
    method that could replace or erase a row here would silently rewrite
    that history out from under every formula that assumes it only ever
    grows.
    """

    model = RoadObservation


class RoadHealthRepository(AppendOnlyRepository[RoadHealth]):
    """Adds nothing beyond what `AppendOnlyRepository` provides -- deliberately (SCHM-02, D-08).

    RoadHealth rows are point-in-time health measurements. Phase 6's
    deterioration-rate calculation and Phase 8's forecast-accuracy tracking
    both depend on every prior measurement remaining exactly as recorded --
    a method that could replace or erase one would corrupt the trend they
    are computed from.
    """

    model = RoadHealth


class PredictionRepository(AppendOnlyRepository[Prediction]):
    """Adds nothing beyond what `AppendOnlyRepository` provides -- deliberately (SCHM-02, D-08).

    Prediction rows are forecasts recorded at the moment they were made.
    FCST-03's accuracy tracking joins a Prediction row against a later
    RoadHealth row to see how the forecast actually played out -- that
    comparison is meaningless if a Prediction's original values could ever
    be changed after the fact to match what really happened.
    """

    model = Prediction
