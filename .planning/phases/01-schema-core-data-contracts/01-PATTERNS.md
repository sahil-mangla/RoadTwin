# Phase 1: Schema & Core Data Contracts - Pattern Map

**Mapped:** 2026-09-22
**Files analyzed:** 20 (target files this phase creates)
**Analogs found:** 0 / 20 — **greenfield repository, no existing code**

## Codebase Status

Confirmed via `find /Users/sahilmangla/RoadTwin -maxdepth 2` (excluding `.planning/` and `.git/`): the only existing content is `.claude/CLAUDE.md`. There is no `backend/` directory, no source files, no prior models/services/routes of any kind. This is the **first implementation phase** of the project — there are no existing analogs anywhere in this repository to copy patterns from.

Because of this, the planner should **not** expect a "closest analog" column to be populated. Instead, this document serves as:
1. A **file manifest** of every file Phase 1 creates (from RESEARCH.md's Recommended Project Structure, §179-213, cross-checked against CONTEXT.md's locked decisions).
2. The **concrete code patterns** to use for each file, sourced directly from RESEARCH.md's Pattern 1-4 sections and Code Examples (since there is no in-repo analog, RESEARCH.md's cited external patterns — GeoAlchemy2 docs, SQLAlchemy 2.0 discussion #10698 — are the closest thing to "patterns to copy from" available).

All patterns below are traceable to RESEARCH.md sections; none are invented here.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|-----------------|---------------|
| `backend/models/__init__.py` | config (metadata re-export) | N/A | none | no analog (greenfield) |
| `backend/models/base.py` | model (base class + mixins) | N/A | none | no analog (greenfield) |
| `backend/models/enums.py` | model (enum types) | N/A | none | no analog (greenfield) |
| `backend/models/report.py` | model | CRUD | none | no analog (greenfield) |
| `backend/models/detection.py` | model | CRUD | none | no analog (greenfield) |
| `backend/models/road_segment.py` | model | CRUD | none | no analog (greenfield) |
| `backend/models/road_observation.py` | model | CRUD (append-only) | none | no analog (greenfield) |
| `backend/models/road_health.py` | model | CRUD (append-only) | none | no analog (greenfield) |
| `backend/models/prediction.py` | model | CRUD (append-only) | none | no analog (greenfield) |
| `backend/models/maintenance_recommendation.py` | model | CRUD | none | no analog (greenfield) |
| `backend/db/session.py` | config (engine/session factory) | N/A | none | no analog (greenfield) |
| `backend/db/repository.py` | service (repository layer) | CRUD | none | no analog (greenfield) |
| `backend/alembic/env.py` | config (migration wiring) | N/A | none | no analog (greenfield) |
| `backend/alembic/versions/0001_initial_schema.py` | migration | batch (DDL) | none | no analog (greenfield) |
| `backend/alembic.ini` | config | N/A | none | no analog (greenfield) |
| `backend/requirements.txt` | config | N/A | none | no analog (greenfield) |
| `backend/tests/conftest.py` | test (fixtures) | N/A | none | no analog (greenfield) |
| `backend/tests/test_models_roundtrip.py` | test | CRUD | none | no analog (greenfield) |
| `backend/tests/test_append_only.py` | test | N/A | none | no analog (greenfield) |
| `backend/tests/test_migrations.py` | test | batch | none | no analog (greenfield) |
| `docker-compose.yml` (Postgres+PostGIS service only, per D-04) | config | N/A | none | no analog (greenfield) |
| `backend/services/{spatial,intelligence,maintenance}/` | service | N/A | none | stub-only per D-02, no code this phase |
| `backend/routes/` | route | N/A | none | stub-only per D-02, no code this phase |

## Pattern Assignments

Since there are no in-repo analogs, each entry below cites the RESEARCH.md section that is the source of truth for that file's implementation pattern. Planner/executor should treat these as "copy from" sources in lieu of codebase analogs.

### `backend/models/base.py` (model, N/A)

**Source:** RESEARCH.md Pattern 2 (UUID Primary Keys, Client-Side Default), lines 247-263

```python
import uuid
from sqlalchemy.orm import Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
```
Applies to all 7 entity models per D-05 (UUID v4 PKs, client-side `default=uuid.uuid4`, not server-side).

---

### `backend/models/enums.py` (model, N/A)

**Source:** RESEARCH.md Pattern 3 (Status Lifecycle Enum), lines 265-289

```python
import enum

class ReportStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    EVIDENCE_CONFIRMED = "evidence_confirmed"
    REJECTED = "rejected"  # reserved for v2 MODR-01, per D-06
```
Per RESEARCH.md's resolution addendum (line 15), Detection shares this same `ReportStatus` enum type (one shared Postgres enum type, not two). Subclassing `str` alongside `enum.Enum` makes it JSON-serializable directly for reuse as a Pydantic field type.

---

### `backend/models/report.py` (model, CRUD)

**Source:** RESEARCH.md Pattern 1 (GeoAlchemy2 Geometry Column) + Code Examples "Full Report model", lines 221-245, 376-418

```python
import uuid
import datetime as dt
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry, WKBElement
from .base import Base
from .enums import ReportStatus

class Report(Base):
    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    latitude: Mapped[float] = mapped_column(nullable=False)
    longitude: Mapped[float] = mapped_column(nullable=False)
    gps_accuracy_meters: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        sa.Enum(ReportStatus, name="report_status"),
        default=ReportStatus.UNVERIFIED,
        nullable=False,
    )
    timestamp: Mapped[dt.datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    image_path: Mapped[str] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    community_upvotes: Mapped[int] = mapped_column(default=0, nullable=False)
    verification_score: Mapped[float | None] = mapped_column(nullable=True)

    detections: Mapped[list["Detection"]] = relationship(back_populates="report")
```

**IMPORTANT correction to RESEARCH.md's code example:** the example at lines 376-418 uses stale placeholder field names (`image_storage_key`, `submitted_at`) — per CONTEXT.md's Resolution Addendum (RESEARCH.md line 22), use `image_path` and `created_at`+`timestamp` (both fields exist, distinct semantics) instead. Field list is per RESEARCH.md line 14 (confirmed exact field list): `id, image_path, latitude, longitude, timestamp, source, description, community_upvotes, verification_score, status, created_at`, plus additive `location` geometry column and `gps_accuracy_meters`. Do NOT add a citizen-identity FK — that's Phase 2's job.

**PostGIS point construction pitfall** (RESEARCH.md Pitfall 1, lines 346-351): WKT/PostGIS point order is `(longitude, latitude)`, opposite of conversational lat/lng — centralize point construction in one helper (e.g. `make_point(lat, lng)`) to avoid axis-swap bugs.

---

### `backend/models/detection.py` (model, CRUD)

**Source:** RESEARCH.md resolution addendum line 15 (confirmed field list) + Pattern 3 (shared enum)

Fields: `id, report_id (FK -> report.id), damage_type, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2, bbox_area_ratio, severity, status`. `status` uses the same `ReportStatus` enum type as Report (shared Postgres enum type per resolution addendum — simpler, no separate `DetectionStatus` type needed).

---

### `backend/models/road_segment.py` (model, CRUD)

**Source:** RESEARCH.md resolution addendum line 16

Fields: `id, segment_identifier, start_lat, start_lng, end_lat, end_lng, road_name, road_type, length_meters, current_health_score, current_risk_score, deterioration_rate, last_observed_at`, plus additive `Geometry(LINESTRING, 4326)` column derived from the two endpoint pairs (not stored independently — construct via a helper at insert/update time, consistent with Report's point-construction-helper pattern).

---

### `backend/models/road_observation.py`, `road_health.py`, `prediction.py` (model, CRUD append-only)

**Source:** RESEARCH.md resolution addendum lines 17-19 + Pattern 4 (append-only enforcement), lines 291-324

- **RoadObservation:** `id, road_segment_id (FK), report_id (FK), detection_id (FK), observed_at, severity, damage_type, confidence, verification_score, contribution_weight`
- **RoadHealth:** `id (additive UUID PK), road_segment_id (FK), measured_at, health_score, severity_burden, damage_density, evidence_score, deterioration_rate, risk_score`. No `interpretation_band` column — that's a display-time computation, never stored.
- **Prediction:** `id (additive UUID PK), road_segment_id (FK), generated_at, horizon_days, predicted_health_score, failure_probability, confidence, method` (method is a justified additive column for FCST-01 transparency).

All three are FK'd to `RoadSegment` and accessed exclusively through `AppendOnlyRepository` (see `backend/db/repository.py` pattern below) — no `update`/`delete` methods defined anywhere in their data-access path.

---

### `backend/models/maintenance_recommendation.py` (model, CRUD)

**Source:** RESEARCH.md resolution addendum line 20

Fields: `id (additive UUID PK), road_segment_id (FK), priority_score, urgency, recommended_action, generated_at, explanation`. Do NOT add `repair_status` — RPWF-01 is explicitly Phase 7 scope.

---

### `backend/db/repository.py` (service, CRUD)

**Source:** RESEARCH.md Pattern 4 (Repository-Layer Append-Only Enforcement), lines 291-324

```python
from typing import Generic, TypeVar
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def get(self, id) -> T | None: ...
    async def list(self, **filters) -> list[T]: ...

class AppendOnlyRepository(BaseRepository[T]):
    """No update() or delete() — intentionally. Do not add them."""

class RoadObservationRepository(AppendOnlyRepository["RoadObservation"]):
    model = RoadObservation
```
`MutableRepository[T](BaseRepository[T])` additionally defines `update()`, used for Report, Detection, RoadSegment, MaintenanceRecommendation. `AppendOnlyRepository` (no `update`/`delete`) is used exclusively for RoadObservation, RoadHealth, Prediction — enforces D-08 structurally (AttributeError at call site, not a runtime guard).

---

### `backend/alembic/env.py` (config, N/A)

**Source:** RESEARCH.md "Alembic env.py wiring for async app + GeoAlchemy2", lines 420-448, and Pitfall 2 (lines 353-358) + Pitfall 3 (lines 360-365)

```python
from geoalchemy2 import alembic_helpers
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
target_metadata = Base.metadata  # imported from backend/models/__init__.py

def run_migrations_online():
    # Use the SYNC connection string (psycopg), not the app's asyncpg URL
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=alembic_helpers.include_object,
            process_revision_directives=alembic_helpers.writer,
            render_item=alembic_helpers.render_item,
        )
        with context.begin_transaction():
            context.run_migrations()
```
Must wire all three `geoalchemy2.alembic_helpers` (include_object, writer, render_item) into both `run_migrations_online()` and `run_migrations_offline()`. Use a separate sync `DATABASE_URL_SYNC` (`postgresql+psycopg://...`) distinct from the app's async `DATABASE_URL` (`postgresql+asyncpg://...`).

---

### `backend/alembic/versions/0001_initial_schema.py` (migration, batch)

**Source:** RESEARCH.md "Initial migration must enable PostGIS", lines 450-456

```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    # ... then create_geospatial_table / create_table calls for all 7 entities
```
Manually review the autogenerated migration for `Report.location`/`RoadSegment` geometry columns to confirm it emits `create_geospatial_table`/`add_geospatial_column` (GeoAlchemy2's Alembic-op helpers), not a plain `sa.Column(...)`.

---

### `backend/tests/test_append_only.py` (test, N/A)

**Source:** RESEARCH.md Pattern 4 verification test note, line 324

```python
assert not hasattr(RoadObservationRepository, "update")
assert not hasattr(RoadObservationRepository, "delete")
# repeat for RoadHealthRepository, PredictionRepository
```

---

## Shared Patterns

### UUID Primary Keys (all 7 entities)
**Source:** RESEARCH.md Pattern 2, lines 247-263
**Apply to:** every model file — `UUIDPKMixin` from `backend/models/base.py`, client-side `default=uuid.uuid4`, not `server_default=func.gen_random_uuid()`.

### Status Lifecycle Enum (Report, Detection)
**Source:** RESEARCH.md Pattern 3, lines 265-289
**Apply to:** `backend/models/report.py`, `backend/models/detection.py` — shared `ReportStatus` enum type (`unverified → corroborated → evidence_confirmed`, plus `rejected`).

### Append-Only Repository Enforcement (RoadObservation, RoadHealth, Prediction)
**Source:** RESEARCH.md Pattern 4, lines 291-324
**Apply to:** `backend/db/repository.py`'s `AppendOnlyRepository` class and its three subclasses — structural, not a runtime guard.

### GeoAlchemy2 Geometry Columns (Report, RoadSegment)
**Source:** RESEARCH.md Pattern 1, lines 221-245
**Apply to:** `Report.location` (`Geometry(POINT, 4326)`), `RoadSegment` (`Geometry(LINESTRING, 4326)` derived from endpoint pairs). Always pair Report's geometry with the nullable `gps_accuracy_meters` column. Centralize lng/lat axis-order handling in one `make_point()` helper (Pitfall 1).

### Sync vs Async DB Driver Split (Alembic)
**Source:** RESEARCH.md Pitfall 3, lines 360-365
**Apply to:** `backend/db/session.py` (asyncpg, app runtime) vs `backend/alembic/env.py` (psycopg v3 sync, migrations only) — two separate connection strings in settings.

## No Analog Found

All 20+ files listed above have no analog — this is the first phase of a greenfield repository. Planner should treat the "Source" citations to RESEARCH.md sections in each Pattern Assignment above as the substitute for codebase analogs.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| All files listed in File Classification | (various) | (various) | Repository confirmed empty prior to this phase (only `.claude/CLAUDE.md` exists outside `.planning/`) — no prior backend code of any kind to draw analogs from. |

## Metadata

**Analog search scope:** Full repository root (`/Users/sahilmangla/RoadTwin`), confirmed via `find -maxdepth 2` excluding `.planning/` and `.git/`.
**Files scanned:** 1 non-planning file found (`.claude/CLAUDE.md`, not a code analog).
**Pattern extraction date:** 2026-09-22
