"""Repository layer -- the structural enforcement point for D-08/SCHM-02.

Every query is built with SQLAlchemy `select()` constructs and bound
parameters; no value is ever interpolated into query text (threat T-01-03).
"""

from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.geo import make_point
from backend.models.report import Report

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

    async def list(self, limit: int = 50, **filters) -> list[T]:
        stmt = sa.select(self.model)
        for field, value in filters.items():
            stmt = stmt.where(getattr(self.model, field) == value)
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
