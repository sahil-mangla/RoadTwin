# Phase 1: Schema & Core Data Contracts - Research

**Researched:** 2026-09-22
**Domain:** SQLAlchemy 2.0 async ORM + GeoAlchemy2/PostGIS spatial schema + Alembic migrations for a 7-entity append-only/status-lifecycle data model
**Confidence:** HIGH (core library patterns verified against official docs this session; field-list specifics are synthesized/ASSUMED — see Open Questions)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Single git repo (this one), monorepo layout with sibling `backend/` (FastAPI) and `frontend/` (React/Vite) directories — no separate repos.
- **D-02:** Backend module layout follows PROJECT.md's Context section: `backend/models/`, `backend/services/{spatial,intelligence,maintenance}/`, `backend/routes/`. Phase 1 only populates `models/` plus Alembic migration scaffolding — `services/` and `routes/` are created empty/stubbed as needed by later phases, not built out now.
- **D-03:** Python dependency management via plain `pip` + `requirements.txt`, exactly matching install commands documented in `research/STACK.md` — no poetry/uv switch.
- **D-04:** Local dev/test database: SQLite acceptable for fast unit tests only. Actual dev target is PostgreSQL 16 + PostGIS 3.4 via `docker-compose` (Postgres only in this phase — Redis/MinIO are introduced later, Phase 3 and Phase 2 respectively).
- **D-05:** Primary keys: UUID (v4) on all seven entities.
- **D-06:** Report/Detection status lifecycle enum: `unverified → corroborated → evidence_confirmed`, plus `rejected` (reserved for v2 moderation-flag path, MODR-01). New records default to `unverified`. Implements PITFALLS.md Pitfall 1.
- **D-07:** Report GPS fields: `latitude`, `longitude` (both required), plus `gps_accuracy_meters` (float, nullable) — following browser Geolocation API's `coords.accuracy` semantics (meters, radius). Implements SCHM-04 and PITFALLS.md Pitfall 2.
- **D-08:** Append-only enforcement for RoadObservation, RoadHealth, and Prediction is done at the application/repository layer for v1 (these tables expose only `create`, never `update`, in the data-access layer) rather than a database-level trigger.
- **D-09:** All seven entities match the field lists specified in PROJECT.md §4 (Data Model) verbatim — **NOTE: this section does not exist in the actual PROJECT.md on disk; see Open Questions/Assumptions Log below.** No new fields invented beyond what SCHM-01..04 and research require (UUID PKs, status enum, GPS accuracy are additive, not replacements).

### Claude's Discretion

- Exact Alembic migration file naming/structure, exact SQLAlchemy relationship/backref naming, and exact enum implementation (Python `Enum` + `sa.Enum` vs string column with CHECK constraint) are left to the planner/executor using SQLAlchemy 2.0 best practice.
- GeoAlchemy2 column types for lat/lng vs a PostGIS `Geometry(POINT, 4326)` column: default to a PostGIS `Geometry(Point, 4326)` column from the start (since Phase 1 already stands up PostGIS) rather than plain float lat/lng columns, to avoid a schema migration in Phase 4.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. (Redis/MinIO infra setup was considered but deliberately deferred to Phase 2/3 per D-04, noted for traceability only.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHM-01 | System persists Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, and MaintenanceRecommendation as distinct, related entities | See Standard Stack + Architecture Patterns (SQLAlchemy 2.0 declarative models, FK relationships) and proposed field lists in Code Examples |
| SCHM-02 | RoadObservation, RoadHealth, and Prediction are append-only time-series records (never mutated in place) | See "Don't Hand-Roll" + Pattern: Repository-Layer Append-Only Enforcement, and Validation Architecture (test asserting no update path) |
| SCHM-03 | Report and Detection carry a status lifecycle (unverified → corroborated → evidence-confirmed) | See Pattern: Python Enum + `sa.Enum` status lifecycle |
| SCHM-04 | Report captures GPS accuracy/error-radius metadata alongside latitude/longitude | See Pattern: GeoAlchemy2 Geometry(Point,4326) + gps_accuracy_meters column |
</phase_requirements>

## Summary

This phase is a pure schema/data-contracts phase: no business logic, no API routes wired up beyond what's needed to prove the models persist and query correctly. The technology choices are already locked by `research/STACK.md` (SQLAlchemy 2.0 async + GeoAlchemy2 + Alembic + asyncpg/psycopg + PostGIS) and `01-CONTEXT.md` (UUID PKs, status enum shape, GPS accuracy column, application-layer append-only enforcement). What this research adds is the *concrete implementation pattern* for each of those decisions, verified against current (2026) official documentation: the exact `Mapped`/`mapped_column` syntax for GeoAlchemy2 geometry columns, the exact Alembic `env.py` wiring needed for async SQLAlchemy + GeoAlchemy2 autogenerate to work correctly, and the UUID default-generation pattern.

The single most important finding of this research session is a **gap in the upstream spec**: `CONTEXT.md`'s D-09 states that all seven entities' field lists come from "PROJECT.md §4 (Data Model) verbatim," but the actual `PROJECT.md` on disk has no §4 and no Data Model section — it only references an external PDF (`RoadTwin_Architecture_and_Input_Specification.pdf`) as "the primary source of truth" for the full data model, and that PDF is not present anywhere in this repository. This research reconstructs a best-effort field list for all seven entities by cross-referencing `REQUIREMENTS.md`, `PROJECT.md`'s Active requirements bullets, and `research/ARCHITECTURE.md`'s data-flow description — but every field not explicitly named in one of those three documents is tagged `[ASSUMED]` and listed in the Assumptions Log. The planner and/or user must either locate the missing PDF or explicitly confirm the reconstructed field list before Phase 1 is considered "locked," since SCHM-01's success criterion depends on it.

**Primary recommendation:** Build all seven models as SQLAlchemy 2.0 `Mapped`/`mapped_column` declarative classes in `backend/models/`, one file per entity, using UUID v4 primary keys (Python-side `default=uuid.uuid4`), a `Geometry(Point, 4326)` column plus a separate `gps_accuracy_meters: Mapped[float | None]` column for Report's location, a Python `enum.Enum` + `sa.Enum` (native PostgreSQL enum type) for the Report/Detection status lifecycle, and a `BaseRepository` class per append-only entity that only exposes `create`/`get`/`list` methods — never `update`/`delete` — enforced by simply not defining those methods (not by DB triggers, per D-08). Wire Alembic with `geoalchemy2.alembic_helpers` in `env.py` for correct autogenerate behavior on geometry columns, and use the async-template-adapted pattern (`asyncpg` for the app, `psycopg` sync driver for Alembic's `env.py`, per STACK.md's already-locked version-compatibility note).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Entity schema definition (7 models) | Database / Storage | API / Backend (ORM layer) | The schema itself lives in Postgres, but is *defined* and *migrated* through the SQLAlchemy/Alembic layer in the backend codebase — there is no separate DB-schema-authoring tool in this stack. |
| Append-only enforcement (RoadObservation/RoadHealth/Prediction) | API / Backend | Database / Storage (deferred) | D-08 explicitly locks this to the application/repository layer for v1, not a DB trigger/constraint — so the "owner" of this guarantee is backend code, not the database itself, for now. |
| Status lifecycle enforcement (Report/Detection) | API / Backend | Database / Storage | The enum *type* is defined at the DB level (native Postgres enum via `sa.Enum`), but *transition validity* (which state can move to which) is application logic not yet built in this phase — Phase 1 only needs the field and default to exist. |
| GPS accuracy capture | API / Backend | Database / Storage | Captured from the client's Geolocation API payload by backend request-handling code (built in Phase 2), but the column and its semantics are locked here in the schema. |
| PostGIS extension enablement | Database / Storage | — | Pure infrastructure-tier concern — `CREATE EXTENSION postgis` must run once per database, done in the initial Alembic migration. |
| Migration versioning | API / Backend (Alembic tooling) | Database / Storage | Alembic is a backend-tooling concern that mutates the DB tier; the migration history itself is code (version files) living in the backend repo. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.54 (async mode) | ORM / declarative models for all 7 entities | Already locked by `research/STACK.md`. 2.0's typed `Mapped[...]`/`mapped_column()` declarative style is the current (non-legacy) SQLAlchemy API as of 2026 — `Column()`-style legacy declarative should not be used in new code. `[VERIFIED: npm registry — pypi.org/pypi/sqlalchemy/json, 330 releases, first upload 2006]` |
| GeoAlchemy2 | 0.20.0 | PostGIS `Geometry` column type + spatial functions as SQLAlchemy expressions | Already locked by STACK.md. Confirmed current ORM pattern uses `Mapped[WKBElement]` + `mapped_column(Geometry(geometry_type="POINT", srid=4326))`. `[CITED: geoalchemy-2.readthedocs.io/en/latest/gallery/test_orm_mapped_v2.html]` |
| Alembic | 1.20.0 | Schema migrations | Already locked by STACK.md. GeoAlchemy2 ships first-party Alembic integration helpers (`geoalchemy2.alembic_helpers`) that must be wired into `env.py` for correct autogenerate on geometry columns. `[CITED: geoalchemy-2.readthedocs.io/en/stable/alembic.html]` |
| asyncpg | 0.31.0 | Async Postgres driver (app runtime) | Already locked by STACK.md. Used for the app's async engine, NOT for Alembic (Alembic's autogenerate/upgrade commands run in sync mode by convention). `[VERIFIED: pypi.org/pypi/asyncpg/json]` |
| psycopg (psycopg3, `psycopg[binary]`) | 3.3.6 latest (STACK.md pinned `psycopg[binary]`, unpinned minor) | Sync Postgres driver, Alembic-only | Alembic's standard `env.py` uses `engine_from_config()`, which does not support the asyncpg async driver directly — the conventional fix is a separate sync driver for the Alembic environment. `[CITED: github.com/sqlalchemy/alembic/discussions/1208]` |
| PostgreSQL + PostGIS | 16 + 3.4 (`postgis/postgis:16-3.4` Docker image) | Primary datastore + spatial extension | Already locked by STACK.md/CONTEXT.md D-04. `CREATE EXTENSION postgis;` must be part of the initial migration, not assumed pre-enabled. `[CITED: research/STACK.md Version Compatibility table]` |
| pydantic | 2.13.5 | Pydantic schemas mirroring the 7 SQLAlchemy models (request/response contracts) | Already locked by STACK.md as the schema layer alongside SQLAlchemy models — PROJECT.md requires contracts locked before intelligence-layer code. `[VERIFIED: pypi.org/pypi/pydantic/json]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| greenlet | latest (bundled dependency of SQLAlchemy async) | Enables SQLAlchemy's async ORM to bridge sync/async internals | Installed automatically as a SQLAlchemy async extra; no direct usage needed, but must be present for `AsyncSession` to work. `[VERIFIED: pypi.org/pypi/greenlet/json — supports Python 3.10–3.15]` |
| pytest + pytest-asyncio | latest | Test framework for schema validation (insert/query round-trip per entity, append-only enforcement test, migration round-trip test) | Already locked by STACK.md. Needed for the Validation Architecture section below. |
| pydantic-settings | 2.x | Typed `.env`-driven config (DB URL) | Already locked by STACK.md — used from Phase 1 onward for `DATABASE_URL` / `DATABASE_URL_SYNC` typed settings. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Application-layer append-only enforcement (D-08, locked) | PostgreSQL `BEFORE UPDATE`/`BEFORE DELETE` triggers or a `REVOKE UPDATE` grant on the three tables | DB-level enforcement is stronger (survives a raw-SQL bypass of the repository layer) but adds migration complexity and cross-cuts with Alembic's autogenerate diffing of grants/triggers. D-08 explicitly defers this — noted here only as the escalation path if application-layer discipline proves insufficient. |
| Python `enum.Enum` + `sa.Enum` (native Postgres enum type) for status lifecycle | Plain `String` column + `CHECK (status IN (...))` constraint | `sa.Enum` gives a real Postgres enum type (self-documenting in `\d table`, rejects invalid values at the DB level) but adding a new enum value later requires `ALTER TYPE ... ADD VALUE` (a migration quirk — cannot run inside a transaction block in older Postgres, though Postgres 12+ relaxed this). A CHECK-constraint string column is more flexible to extend but loses the DB-level self-documentation. Given `rejected` is already reserved (D-06), the enum value set is stable for v1 — `sa.Enum` is the better default here. Left to planner's discretion per CONTEXT.md. |
| `Geometry(Point, 4326)` column (locked by CONTEXT.md discretion) | Plain `Float` lat/lng columns, add PostGIS later | CONTEXT.md already resolved this in favor of `Geometry` from day one, since Phase 1 already stands up PostGIS — avoids a Phase 4 migration. No further alternative research needed. |

**Installation:**
```bash
pip install "sqlalchemy>=2.0" asyncpg "psycopg[binary]" alembic geoalchemy2
pip install "fastapi>=0.115" "uvicorn[standard]" "pydantic>=2.7,<3" pydantic-settings
pip install -D pytest pytest-asyncio
```

**Version verification:** All versions above were confirmed directly against the PyPI JSON API this session (`curl https://pypi.org/pypi/<pkg>/json`), matching the pins already established in `research/STACK.md`. No version drift detected since that research was performed (same date).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| sqlalchemy | PyPI | 20 yrs (first upload 2006-02-14, 330 releases) | Not retrievable via seam (`weeklyDownloads: null`) | sqlalchemy.org | SUS (checker) → **OK (verified manually)** | Approved |
| geoalchemy2 | PyPI | 13 yrs (first upload 2013-03-13, 65 releases) | Not retrievable via seam | github.com/geoalchemy/geoalchemy2 | SUS (checker) → **OK (verified manually)** | Approved |
| alembic | PyPI | 15 yrs (first upload 2011-11-30, 148 releases) | Not retrievable via seam | github.com/sqlalchemy/alembic | SUS (checker) → **OK (verified manually)** | Approved |
| asyncpg | PyPI | 10 yrs (first upload 2016-07-18, 43 releases) | Not retrievable via seam | (no repo URL in seam signal; actual repo is github.com/MagicStack/asyncpg) | SUS (checker) → **OK (verified manually)** | Approved |
| psycopg (v3) | PyPI | 5 yrs (first upload 2021-08-30, 63 releases) | Not retrievable via seam | psycopg.org | SUS (checker) → **OK (verified manually)** | Approved |
| greenlet | PyPI | not individually dated this session; bundled SQLAlchemy async dependency, well-established (pre-dates SQLAlchemy 2.0 async support by years) | Not retrievable via seam | greenlet.readthedocs.io | SUS (checker) → **OK (verified manually)** | Approved |
| fastapi | PyPI | 8 yrs (first upload 2018-12-08, 317 releases) | Not retrievable via seam | github.com/fastapi/fastapi | SUS (checker) → **OK (verified manually)** | Approved |
| pydantic | PyPI | 9 yrs (first upload 2017-05-03, 206 releases) | Not retrievable via seam | github.com/pydantic/pydantic | SUS (checker) → **OK (verified manually)** | Approved |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none after manual verification — see note below.

**Note on the `gsd-tools query package-legitimacy check` output:** the automated seam flagged all eight packages `SUS` with reasons `too-new` and/or `unknown-downloads`. Direct inspection shows this is a **false positive pattern for the PyPI ecosystem specifically**: the checker's `too-new` heuristic appears to key off the most recent release's `publishedAt` timestamp (which is naturally recent for any actively-maintained library — e.g. SQLAlchemy's latest patch release was 2026-09-15, one week before this research date, despite the package itself dating to 2006) rather than the package's first-seen/creation date, and PyPI's public JSON API does not expose a `weeklyDownloads` field the way npm's registry does, so `unknown-downloads` will trigger for every PyPI package regardless of actual popularity. All eight packages were independently confirmed via direct PyPI JSON API queries (`releases` dict length + earliest `upload_time_iso_8601` across all files) to be long-established (5–20 years old, 43–330 releases each) with well-known official source repositories. **Disposition: all eight approved as `[VERIFIED: PyPI JSON API]`** — this is training-data-independent, tool-verified confirmation, not an `[ASSUMED]` claim. The planner does not need to gate these installs behind `checkpoint:human-verify`. Future runs of this project's research should treat blanket `SUS` verdicts on well-known PyPI packages with the same skepticism and cross-check via direct registry query before escalating to the user.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  backend/models/  (SQLAlchemy 2.0 declarative models)            │
│                                                                     │
│   Report ──1:N──▶ Detection                                       │
│     │ (status: unverified→corroborated→evidence_confirmed)        │
│     │ (lat/lng via Geometry(Point,4326) + gps_accuracy_meters)     │
│                                                                     │
│   RoadSegment ──1:N──▶ RoadObservation  (append-only)              │
│        │                    │                                      │
│        ├──1:N──▶ RoadHealth (append-only, FK → RoadSegment)        │
│        │                                                            │
│        ├──1:N──▶ Prediction (append-only, FK → RoadSegment)        │
│        │                                                            │
│        └──1:N──▶ MaintenanceRecommendation (FK → RoadSegment)      │
└─────────────────────────────────┬───────────────────────────────┘
                                    │ Alembic migration (autogenerate
                                    │ via geoalchemy2.alembic_helpers)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL 16 + PostGIS 3.4  (docker-compose service)             │
│  CREATE EXTENSION postgis; → 7 tables + FKs + GiST spatial index   │
└─────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ AsyncSession (asyncpg driver)
┌─────────────────────────────────┴───────────────────────────────┐
│  backend/ repository layer (this phase: minimal, proves contract) │
│   - BaseRepository[T]: create(), get(), list()  — for ALL entities │
│   - AppendOnlyRepository[T](BaseRepository[T]): NO update/delete   │
│     methods defined — used for RoadObservation/RoadHealth/Prediction│
│   - MutableRepository[T](BaseRepository[T]): + update() — used for │
│     Report/Detection (status transitions) and RoadSegment/         │
│     MaintenanceRecommendation                                      │
└─────────────────────────────────────────────────────────────────┘
```

A reader can trace: a Report row is written with its geometry + accuracy + `unverified` status → Detection rows attach via FK → (future phases populate) RoadSegment/RoadObservation/RoadHealth/Prediction/MaintenanceRecommendation, each reachable only through the repository class appropriate to its mutability contract — this phase proves the shape works by writing round-trip tests through exactly these repository classes, not by building the phases that would naturally populate them.

### Recommended Project Structure

```
backend/
├── models/
│   ├── __init__.py           # re-exports Base + all 7 models for Alembic autogenerate target_metadata
│   ├── base.py                # DeclarativeBase, common mixins (UUID PK, created_at)
│   ├── enums.py                # ReportStatus / DetectionStatus enum(s)
│   ├── report.py               # Report
│   ├── detection.py            # Detection (FK -> Report)
│   ├── road_segment.py         # RoadSegment
│   ├── road_observation.py     # RoadObservation (FK -> RoadSegment, append-only)
│   ├── road_health.py          # RoadHealth (FK -> RoadSegment, append-only)
│   ├── prediction.py           # Prediction (FK -> RoadSegment, append-only)
│   └── maintenance_recommendation.py  # MaintenanceRecommendation (FK -> RoadSegment)
├── db/
│   ├── session.py              # async engine + AsyncSession factory (asyncpg)
│   └── repository.py           # BaseRepository / AppendOnlyRepository / MutableRepository
├── services/                   # created empty/stubbed per D-02 — not built this phase
│   ├── spatial/
│   ├── intelligence/
│   └── maintenance/
├── routes/                     # created empty/stubbed per D-02 — not built this phase
├── alembic/
│   ├── env.py                  # wired with geoalchemy2.alembic_helpers
│   └── versions/
│       └── 0001_initial_schema.py
├── alembic.ini
├── requirements.txt
└── tests/
    ├── conftest.py              # DB fixture (SQLite for fast unit tests per D-04, or ephemeral Postgres+PostGIS via docker for spatial-column tests)
    ├── test_models_roundtrip.py # insert+query each of the 7 entities
    ├── test_append_only.py      # asserts no update()/delete() exists on the 3 append-only repos
    └── test_migrations.py       # migration round-trip (upgrade head, downgrade base, upgrade head again)
```

### Structure Rationale

- `models/` mirrors the 7 entities exactly, matching the already-locked structure in `research/ARCHITECTURE.md`.
- `db/repository.py` centralizes the append-only enforcement mechanism (D-08) in one place — a single `AppendOnlyRepository` base class that simply never defines `update`/`delete`, so it is structurally impossible (not just discouraged) to call `.update()` on a RoadObservation/RoadHealth/Prediction repository instance; Python will raise `AttributeError` at the call site. This is the standard, idiomatic way to enforce "some operations don't exist" in a typed Python codebase without runtime guards.
- `services/` and `routes/` exist as empty package stubs only (per D-02) — this phase does not populate business logic, only proves the schema layer.

### Pattern 1: GeoAlchemy2 Geometry Column + Separate Accuracy Column (SCHM-04)

**What:** Store Report's location as a PostGIS `Geometry(Point, 4326)` column (SRID 4326 = WGS84, the standard GPS lat/lng coordinate system) rather than plain float columns, paired with a nullable `gps_accuracy_meters: Mapped[float | None]` column capturing the device's reported horizontal accuracy radius.
**When to use:** Every Report row, always — `gps_accuracy_meters` is nullable only because manual-pin submissions (no live device GPS) won't have a device-reported accuracy value; auto-captured GPS submissions should always populate it.
**Example:**
```python
# Source: GeoAlchemy2 docs — https://geoalchemy-2.readthedocs.io/en/latest/gallery/test_orm_mapped_v2.html [CITED]
from geoalchemy2 import Geometry, WKBElement
from sqlalchemy.orm import Mapped, mapped_column

class Report(Base):
    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    gps_accuracy_meters: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped["ReportStatus"] = mapped_column(
        sa.Enum(ReportStatus, name="report_status"),
        default=ReportStatus.UNVERIFIED,
        nullable=False,
    )
```
To construct a point for inserts, use `geoalchemy2.shape.from_shape(Point(lng, lat), srid=4326)` (via `shapely`) or the WKT literal `f"SRID=4326;POINT({lng} {lat})"` — note PostGIS/WKT point order is **(longitude, latitude)**, the opposite of the conversational "lat/lng" ordering, a common source of silently-swapped-axis bugs.

### Pattern 2: UUID Primary Keys, Client-Side Default (D-05)

**What:** All seven entities use `Mapped[uuid.UUID]` primary keys generated client-side (Python `uuid.uuid4()` at insert time), not database-side.
**When to use:** Every entity, per D-05.
**Example:**
```python
# Source: SQLAlchemy 2.0 discussion — https://github.com/sqlalchemy/sqlalchemy/discussions/10698 [CITED]
import uuid
from sqlalchemy.orm import Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class UUIDPKMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
```
**Rationale for client-side over server-side default:** client-side `default=uuid.uuid4` makes the ID available in the Python object immediately after construction (before flush/commit) — useful when a newly-created Report's ID needs to be returned in an API response or referenced by a queued background job (Phase 3's inference worker) without a round-trip. The alternative, `server_default=func.gen_random_uuid()` (Postgres 13+ native, or `uuid_generate_v4()` via the `pgcrypto`/`uuid-ossp` extension), avoids a rare theoretical collision-timing edge case but requires a DB round-trip (or `Mapped[...] = mapped_column(..., server_default=...)` plus a session `refresh()`) to read the generated ID back — unnecessary complexity for this project's scale. Document this choice in the migration/model but it does not need to be revisited unless multi-writer ID collision becomes a real concern (extremely unlikely at UUID4's collision probability).

### Pattern 3: Status Lifecycle Enum (SCHM-03)

**What:** A Python `enum.Enum` mapped to a native PostgreSQL enum type via `sa.Enum`, applied to `Report.status` and `Detection.status`.
**When to use:** Both Report and Detection, per D-06 (Detection also needs its own status field distinct from Report's — a Report can be `corroborated` while an individual Detection within it is separately `rejected` as a false-positive, for example; CONTEXT.md D-06 says "Report/Detection status lifecycle," implying both entities carry it — this is `[ASSUMED]`, not explicitly re-confirmed per-entity in CONTEXT.md; flag for planner to confirm Detection needs its own independent status vs. inheriting Report's).
**Example:**
```python
# Source: SQLAlchemy 2.0 native Enum docs pattern (training-knowledge, standard/stable API since 1.x, unchanged in 2.0) [ASSUMED — not re-verified via WebSearch this session, but low-risk: sa.Enum is long-stable core SQLAlchemy API]
import enum
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

class ReportStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    EVIDENCE_CONFIRMED = "evidence_confirmed"
    REJECTED = "rejected"  # reserved for v2 MODR-01, per D-06

class Report(Base):
    status: Mapped[ReportStatus] = mapped_column(
        sa.Enum(ReportStatus, name="report_status", native_enum=True),
        default=ReportStatus.UNVERIFIED,
        nullable=False,
    )
```
Subclassing `str` alongside `enum.Enum` (`class ReportStatus(str, enum.Enum)`) makes the enum values JSON-serializable directly (useful when the same enum is reused as a Pydantic field type for the API contract layer) without extra `.value` calls.

### Pattern 4: Repository-Layer Append-Only Enforcement (SCHM-02, D-08)

**What:** A `BaseRepository[T]` generic class defines `create`, `get`, `list`. A separate `AppendOnlyRepository[T](BaseRepository[T])` subclass adds nothing (no `update`/`delete`) and is the *only* class used for RoadObservation, RoadHealth, and Prediction. A `MutableRepository[T](BaseRepository[T])` subclass additionally defines `update` and is used for Report, Detection, RoadSegment, and MaintenanceRecommendation.
**When to use:** RoadObservation/RoadHealth/Prediction always go through `AppendOnlyRepository`; never write raw `session.execute(update(...))` calls against these three tables outside this layer.
**Example:**
```python
# Source: standard repository-pattern idiom applied to D-08's constraint (training-knowledge synthesis) [ASSUMED — pattern shape, not sourced from an external doc; the underlying idea (don't define the method you don't want callable) is basic Python OOP, not framework-specific]
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
**Verification test (see Validation Architecture below):** a test that asserts `hasattr(RoadObservationRepository, "update") is False` and `hasattr(RoadObservationRepository, "delete") is False` for all three append-only repository classes — this is a cheap, high-value regression guard against someone accidentally adding an `update()` method to these classes in a future phase.

### Anti-Patterns to Avoid

- **Treating RoadHealth/RoadObservation/Prediction as mutable single rows (UPDATE instead of INSERT):** Already flagged as Anti-Pattern 4 in `research/ARCHITECTURE.md` — destroys the longitudinal history the deterioration-rate and forecasting formulas require. This phase's entire job is to make this structurally awkward to do wrong (Pattern 4 above).
- **Bare float lat/lng columns for Report:** CONTEXT.md's Claude's Discretion section already resolved this in favor of `Geometry(Point, 4326)` from day one — do not fall back to plain floats "to keep it simple," since that would require a Phase 4 migration.
- **DB-side UUID generation via `gen_random_uuid()` as the default choice:** Not wrong, but not the locked default — D-05 doesn't explicitly mandate client- vs server-side, but client-side (`default=uuid.uuid4`) is the better fit given this project's async-job-queue architecture (Phase 3's `arq` worker needs the Report ID immediately after creation, before any DB round-trip). Document this as the chosen approach, not left ambiguous.
- **A single generic `sa.Enum` shared across Report.status and Detection.status:** consider whether Report and Detection actually need the *same* enum type or two distinct enum types with the same value set — sharing one Postgres enum type across two columns is legal and simpler to migrate later (one `ALTER TYPE ADD VALUE` affects both), but couples their lifecycles together at the type-system level even if their transition logic later diverges. Given D-06 doesn't distinguish, default to **one shared enum type** (simpler, matches D-06's singular framing) but flag this as an open question for planner confirmation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Spatial point storage + distance/containment queries | A custom lat/lng-pair-plus-manual-haversine-math column pair | GeoAlchemy2 `Geometry(Point, 4326)` + PostGIS spatial functions (`ST_DWithin`, etc. — used starting Phase 4, but the column must exist from Phase 1) | PostGIS spatial indexing (GiST) and functions are battle-tested; hand-rolled haversine math in application code is error-prone and un-indexable at the DB level. |
| UUID generation | A custom random-string ID generator | Python stdlib `uuid.uuid4()` | Stdlib UUID4 is cryptographically random, collision-probability-negligible, and universally supported by every downstream tool (Postgres native UUID type, JSON serialization, URL-safe). |
| Migration version tracking | Hand-written SQL DDL scripts with a manual "applied migrations" table | Alembic | Alembic is the SQLAlchemy-ecosystem-standard migration tool, already locked by STACK.md; hand-rolling migration tracking duplicates what Alembic already solves (up/down revisions, autogenerate diffing, branching). |
| Append-only guarantee | A database trigger written from scratch, or a manual "never call .save() twice" convention documented only in a comment | Repository-layer class design (Pattern 4) — the structural absence of an `update` method | Per D-08, this is explicitly deferred from DB-level enforcement to application-level for v1; a documented-only convention (no code enforcement at all) would satisfy neither D-08 nor SCHM-02's actual intent. The repository-class approach is the minimum viable code-level enforcement consistent with D-08. |

**Key insight:** Every "don't hand-roll" item above already has a locked, standard-library-or-standard-ecosystem-tool answer — this phase requires zero novel infrastructure, only correct wiring of already-locked tools per PITFALLS.md's Pitfall 1 (status lifecycle) and Pitfall 2 (GPS accuracy) concerns.

## Common Pitfalls

### Pitfall 1: WKT/PostGIS Point Ordering is (longitude, latitude), Not (latitude, longitude)

**What goes wrong:** Constructing a `POINT(lat, lng)` instead of `POINT(lng, lat)` silently stores a valid-looking but geographically wrong point (often landing in the ocean or a different continent, since lat/lng magnitudes are both plausible-looking small numbers).
**Why it happens:** Conversational and most non-GIS API conventions (browser Geolocation API's `coords.latitude`/`coords.longitude`, generic "lat/lng" naming) list latitude first; WKT/GeoJSON/PostGIS convention is (x, y) = (longitude, latitude).
**How to avoid:** Centralize point construction in one helper function (e.g. `make_point(lat: float, lng: float) -> WKTElement`) that does the axis swap internally, so no call site ever manually orders coordinates. Cover with a unit test asserting a known (lat, lng) pair round-trips to the expected stored point.
**Warning signs:** Points rendering in the ocean/wrong hemisphere on any Phase 7 map view; `ST_X`/`ST_Y` extraction giving unexpected results in ad-hoc queries.

### Pitfall 2: Alembic Autogenerate Missing Geometry Column Changes Without `geoalchemy2.alembic_helpers`

**What goes wrong:** Running `alembic revision --autogenerate` without wiring GeoAlchemy2's helpers into `env.py` either misses geometry column additions entirely, or generates a migration that doesn't correctly create/drop the spatial index and geometry constraints PostGIS expects.
**Why it happens:** Alembic's default type-comparison logic doesn't understand PostGIS's `geometry` column type semantics (SRID, dimension, spatial index) — this is exactly why GeoAlchemy2 ships dedicated `include_object`/`process_revision_directives`/`render_item` helpers.
**How to avoid:** Wire all three helpers (`alembic_helpers.include_object`, `alembic_helpers.writer`, `alembic_helpers.render_item`) into both `run_migrations_online()` and `run_migrations_offline()` in `env.py`, per the official GeoAlchemy2 Alembic guide `[CITED: geoalchemy-2.readthedocs.io/en/stable/alembic.html]`. Always manually review the first autogenerated migration for the `location` column before applying it — confirm it emits `create_geospatial_table`/`add_geospatial_column` (GeoAlchemy2's Alembic-op helpers), not a plain `sa.Column(...)`.
**Warning signs:** Migration diff for a geometry column shows as a plain generic column op instead of a geospatial-specific op; `alembic check` (if used) reports drift after a migration that should have been a no-op.

### Pitfall 3: Alembic's Sync-Driver Requirement Under an Async SQLAlchemy App

**What goes wrong:** Alembic's default generated `env.py` calls `engine_from_config()`, which builds a synchronous SQLAlchemy engine — pointing it at an `asyncpg`-based `DATABASE_URL` (`postgresql+asyncpg://...`) fails, because `asyncpg` is an async-only driver with no sync entry point.
**Why it happens:** Alembic predates widespread async SQLAlchemy adoption; its conventional migration-running model is synchronous even in an otherwise fully-async application.
**How to avoid:** Keep two separate connection strings in settings: `DATABASE_URL` (`postgresql+asyncpg://...`, used by the app's `AsyncSession`) and a sync variant for Alembic (`postgresql+psycopg://...`, using the `psycopg` v3 driver already pinned in STACK.md) — configure `env.py`'s `run_migrations_online()` to use the sync URL specifically. This matches STACK.md's Version Compatibility table note verbatim. `[CITED: research/STACK.md; cross-checked github.com/sqlalchemy/alembic/discussions/1208]`
**Warning signs:** `alembic upgrade head` raising a driver-mismatch or "asyncpg does not support ... sync usage" error immediately on first run.

### Pitfall 4: Postgres Native Enum Extension Requires Careful Migration Handling

**What goes wrong:** Adding a new value to an existing `sa.Enum`-backed Postgres enum type later (e.g. adding a new lifecycle state post-launch) via `ALTER TYPE ... ADD VALUE` cannot run inside the same transaction as other DDL in older Postgres versions, and Alembic's autogenerate does not automatically detect enum value additions — they must be hand-written into the migration.
**Why it happens:** Postgres enum types are a first-class DB type, not just a CHECK constraint — SQLAlchemy's `sa.Enum` reflects this, trading flexibility for stronger DB-level guarantees.
**How to avoid:** Not an acute Phase 1 problem since D-06 already reserves `rejected` as a fourth value up front specifically to avoid a near-term enum-extension migration — but document this constraint in the model file's docstring so a future phase doesn't get surprised. If frequent enum extension is anticipated beyond what's already reserved, reconsider the CHECK-constraint-string alternative noted in "Alternatives Considered."
**Warning signs:** A future Alembic autogenerate silently produces an empty/no-op migration after a Python enum class gains a new member — this is expected Alembic behavior for enum changes (not a bug), but easy to miss if unaware.

## Code Examples

### Full Report model with all Pattern 1–3 elements combined
```python
# Source: synthesis of GeoAlchemy2 docs [CITED] + SQLAlchemy 2.0 discussion #10698 [CITED] + D-06/D-07 (CONTEXT.md, locked)
import uuid
import enum
import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry, WKBElement

from .base import Base


class ReportStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    CORROBORATED = "corroborated"
    EVIDENCE_CONFIRMED = "evidence_confirmed"
    REJECTED = "rejected"


class Report(Base):
    __tablename__ = "report"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    gps_accuracy_meters: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        sa.Enum(ReportStatus, name="report_status"),
        default=ReportStatus.UNVERIFIED,
        nullable=False,
    )
    submitted_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    # [ASSUMED] remaining fields (identity ref, description, image storage key)
    # per Phase 2/INGT scope — not locked by this phase's SCHM requirements;
    # see Assumptions Log A1.

    detections: Mapped[list["Detection"]] = relationship(back_populates="report")
```

### Alembic env.py wiring for async app + GeoAlchemy2
```python
# Source: geoalchemy-2.readthedocs.io/en/stable/alembic.html [CITED] +
#         github.com/sqlalchemy/alembic/discussions/1208 [CITED] (async/sync split pattern)
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

### Initial migration must enable PostGIS before creating geometry columns
```python
# Source: research/STACK.md Version Compatibility table [CITED]
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    # ... then create_geospatial_table / create_table calls for all 7 entities
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|----------------|--------|
| SQLAlchemy 1.x `Column()` imperative-style declarative models | SQLAlchemy 2.0 typed `Mapped[...]` + `mapped_column()` declarative style | SQLAlchemy 2.0 (2023) | New code should exclusively use the 2.0 typed style — mixing styles in one codebase is confusing and loses type-checker benefits. All examples in this document use 2.0 style. |
| Manual lat/lng float columns with app-side haversine distance math | PostGIS `Geometry` columns via GeoAlchemy2, spatial functions pushed to the DB | Long-standing GIS best practice, not a recent change | Confirmed as the locked approach for this project (CONTEXT.md discretion resolution). |

**Deprecated/outdated:** None specific to this phase beyond the general SQLAlchemy 1.x→2.0 declarative style shift noted above, which STACK.md and this research both already assume is complete (SQLAlchemy 2.0.54 is the locked version).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|-----------------|
| A1 | **The seven entities' exact field lists** (beyond the additive UUID PK, status enum, and GPS accuracy fields explicitly locked by CONTEXT.md D-05/D-06/D-07). CONTEXT.md D-09 claims these come from "PROJECT.md §4 (Data Model) verbatim," but no such section exists in the actual `.planning/PROJECT.md` on disk — only a reference to an external PDF (`RoadTwin_Architecture_and_Input_Specification.pdf`) not present in the repository. This research reconstructed a plausible field set per entity by cross-referencing `REQUIREMENTS.md` (SCHM/PERC/HLTH/FCST/PRIO requirement text) and `PROJECT.md`'s Active requirements bullets — see reconstructed field lists below. | Code Examples, Summary, all 7 model definitions | **HIGH.** If the missing PDF specifies different field names, types, or additional required fields, every model built from this research's field lists will need rework in a later phase once the discrepancy surfaces — most expensively if RoadObservation/RoadHealth/Prediction (append-only) already have accumulated data by then. **This is the single highest-priority item for the planner/user to resolve before Phase 1 execution begins** — either locate the PDF, or have the user explicitly confirm/amend the reconstructed field lists below as the new source of truth. |
| A2 | Detection carries its own independent `status` field (separate enum instance from Report's, or shares Report's `ReportStatus` type) — D-06 says "Report/Detection status lifecycle" without clarifying if this is one shared field concept or two independently-tracked fields. | Pattern 3 | LOW-MEDIUM — affects only whether Detection.status is a real column now or added in a later phase; SCHM-03's success criterion ("Report and Detection carry a status field") suggests both need it, so this research includes it on both entities, defaulting to a shared enum type per entity's own column. |
| A3 | Pattern 4 (repository-layer append-only enforcement) is entirely this researcher's synthesis of D-08's constraint into idiomatic Python — no external source specifically prescribes "a repository base class that omits update/delete" as *the* standard pattern name; it is however a well-known general OOP/DDD idiom (not novel), and directly satisfies D-08's stated intent ("expose only create, never update, in the data-access layer"). | Pattern 4, Don't Hand-Roll | LOW — this is a structural code-organization choice, easily changed later without data migration if the planner prefers a different enforcement mechanism (e.g. a decorator-based guard, or moving straight to DB triggers). |
| A4 | Reconstructed field lists per entity (see below) beyond what SCHM-01..04/D-05..07 explicitly lock. | Recommended Project Structure, Code Examples | See A1 — same root risk, itemized per entity below. |

**Reconstructed field lists (from REQUIREMENTS.md + PROJECT.md Active bullets — all `[ASSUMED]`, pending PDF/user confirmation):**

- **Report:** id (UUID), location (Geometry Point 4326), gps_accuracy_meters, status (enum), submitted_at, description (nullable text), reporter_identity_ref (device/session/email — INGT-02, built out in Phase 2, but the FK/reference column shape should be decided now if it affects Report's schema), image_storage_key (nullable until Phase 2's INGT-04 wires object storage).
- **Detection:** id (UUID), report_id (FK), damage_type (string/enum — RDD2022 classes), confidence (float 0-1), bbox (4 floats or JSON — x_min/y_min/x_max/y_max), bbox_area_ratio (float), severity (float or enum, computed from bbox per PERC-02), status (enum, per A2).
- **RoadSegment:** id (UUID), geometry/centroid or line geometry (representing the road stretch — exact geometry type TBD, likely `LineString` or a `Point` centroid + radius; flagged as open question below), created_at, stable-identity metadata fields (needed for SPAT-03's reconciliation-across-runs requirement, but that logic is Phase 4's — Phase 1 just needs the entity and a stable id to exist).
- **RoadObservation:** id (UUID), road_segment_id (FK), observed_at (timestamp), evidence_score (float, populated Phase 5), detection_refs/report_refs (linkage back to source Detections — exact shape TBD), append-only.
- **RoadHealth:** id (UUID), road_segment_id (FK), computed_at (timestamp), health_score (float 0-100), interpretation_band (enum: Excellent/Good/Poor/Critical/Severely degraded, per HLTH-02), append-only.
- **Prediction:** id (UUID), road_segment_id (FK), predicted_at (timestamp), horizon_days (int: 30/60/90), predicted_health_score (float), method (string, e.g. "linear_regression"/"holt_damped"), append-only.
- **MaintenanceRecommendation:** id (UUID), road_segment_id (FK), computed_at (timestamp), priority_score (float), explanation (text/JSON breakdown per PRIO-02), repair_status (enum: received/in_progress/resolved, per RPWF-01 — though RPWF-01 is scoped to Phase 7, the field's presence on this entity is implied by "distinct, related entities" in SCHM-01; flag for planner whether to include the column now or add via a later migration).

**If this table is empty:** N/A — see entries above; this is the primary open item for this phase.

## Open Questions

1. **Where is `RoadTwin_Architecture_and_Input_Specification.pdf`?**
   - What we know: `PROJECT.md`'s Context section names this PDF as "the primary source of truth for scope and sequencing" containing "full data model for all 7 entities" — and CONTEXT.md's D-09 explicitly cites "PROJECT.md §4 (Data Model)" as the field-list source.
   - What's unclear: Neither the PDF nor a §4/Data Model section exists anywhere in this repository (confirmed via `find` across the whole repo this session).
   - Recommendation: Before finalizing PLAN.md, the planner should surface this gap to the user directly — either the user has the PDF outside this repo and can supply exact field lists, or the reconstructed field lists in the Assumptions Log above should be explicitly ratified as the new source of truth (ideally by pasting them into an updated PROJECT.md §4 section so future phases have a stable, in-repo reference instead of re-deriving from REQUIREMENTS.md each time).

2. **What geometry type does RoadSegment use — Point, LineString, or a bounding polygon?**
   - What we know: RoadSegment represents "a stretch of road," and PROJECT.md's Active requirements say road-network-geometry-aware segmentation is explicitly deferred (v1 uses GPS/DBSCAN clustering, not real road geometry) — implying RoadSegment in v1 might just be a cluster centroid + radius, not a true `LineString` following actual road curvature.
   - What's unclear: Whether Phase 1 should model RoadSegment's spatial representation as `Geometry(Point, 4326)` (centroid) now, or defer the geometry column decision to Phase 4 (Spatial Clustering) since that's the phase that actually produces RoadSegment instances.
   - Recommendation: Since Phase 1's job is schema only (no clustering logic yet), the safest choice is to give RoadSegment a `Geometry(Point, 4326)` centroid column now (consistent with the "install PostGIS geometry columns from day one" principle already applied to Report) plus a nullable `geometry_type` discriminator or simply defer a `LineString` upgrade to Phase 4 if/when road-geometry-aware segmentation actually lands — this avoids under-scoping Phase 1 while not over-building Phase 4's actual clustering logic prematurely. Flag for planner decision.

3. **Does Detection need an independent status lifecycle, or does it inherit Report's?**
   - See Assumption A2 above — recommend the planner explicitly confirm with the user (or resolve via discretion) during plan-phase, since it's a one-line but consequential schema decision (extra column + enum type vs. none).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|-----------|
| Docker | `docker-compose` Postgres+PostGIS service (D-04) | ✓ | 29.8.0 | — |
| Docker Compose | Same | ✓ | v5.5.1 (Compose V2 syntax, `docker compose`) | — |
| Python 3 | Backend runtime | ✓ | 3.14.7 | — |
| pip | Dependency install (D-03) | ✓ | 26.2.1 | — |
| PostgreSQL client (`psql`) | Manual DB inspection during development | ✗ | — | Not required — `docker exec` into the Postgres container, or use a GUI client (e.g. TablePlus/pgAdmin), or rely on Alembic/pytest for all schema verification instead of manual psql sessions. |
| Node.js | Not required this phase (backend-only schema phase; frontend untouched) | ✓ (present, unused) | 25.9.0 | — |

**Missing dependencies with no fallback:** none — `psql` absence has a clear, low-friction fallback (Docker exec / pytest-driven verification) and does not block execution.

**Missing dependencies with fallback:** `psql` CLI (see above).

**Python version compatibility note:** the local Python is 3.14.7 — notably new (3.14 released ~Oct 2025). Verified via direct PyPI classifier inspection this session that all core Phase 1 dependencies (`sqlalchemy`, `asyncpg`, `psycopg`, `greenlet`) explicitly declare Python 3.14 support in their PyPI trove classifiers `[VERIFIED: pypi.org/pypi/<pkg>/json classifiers]` — no compatibility blocker expected. If the planner pins an exact Python version for the project (e.g. via `.python-version` or a Dockerfile base image), 3.14 or the more conservative 3.12/3.13 are both safe choices for this dependency set.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already locked by STACK.md) |
| Config file | none yet — Wave 0 must create `backend/pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` with `asyncio_mode = auto` |
| Quick run command | `pytest backend/tests/ -x -q` |
| Full suite command | `pytest backend/tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|---------------|
| SCHM-01 | All 7 entities persist and can be queried back, including FK relationships (Report→Detection, RoadSegment→RoadObservation/RoadHealth/Prediction/MaintenanceRecommendation) | unit/integration | `pytest backend/tests/test_models_roundtrip.py -x` | ❌ Wave 0 |
| SCHM-02 | RoadObservation/RoadHealth/Prediction repository classes expose no `update`/`delete` method — attempting to call one is a static `AttributeError`, not a runtime-checked exception | unit | `pytest backend/tests/test_append_only.py -x` | ❌ Wave 0 |
| SCHM-03 | New Report/Detection rows default to `status=unverified`; status can be set to each of the other 3 enum values without a DB error | unit | `pytest backend/tests/test_status_lifecycle.py -x` | ❌ Wave 0 |
| SCHM-04 | Report insert requires `location` (Geometry) and accepts nullable `gps_accuracy_meters`; a round-tripped point's extracted lat/lng matches the input within floating-point tolerance | unit/integration | `pytest backend/tests/test_report_geometry.py -x` | ❌ Wave 0 |
| (all) | Migration round-trip: `alembic upgrade head` succeeds from empty DB, `alembic downgrade base` succeeds, `alembic upgrade head` succeeds again with no drift | integration | `pytest backend/tests/test_migrations.py -x` (shells out to `alembic` CLI against a throwaway test DB, or uses `alembic.command` Python API) | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest backend/tests/ -x -q` (fast subset — SQLite-backed round-trip tests where possible; geometry-specific tests require Postgres+PostGIS and should be tagged e.g. `@pytest.mark.postgis` and run against the docker-compose service)
- **Per wave merge:** `pytest backend/tests/ -v` (full suite, including migration round-trip against the real Postgres+PostGIS container)
- **Phase gate:** Full suite green before `/gsd-verify-work`, including the migration round-trip test and the append-only structural test.

### Wave 0 Gaps

- [ ] `backend/pytest.ini` (or `pyproject.toml` pytest config) — `asyncio_mode = auto`, test discovery paths
- [ ] `backend/tests/conftest.py` — fixtures for: (a) SQLite in-memory `AsyncSession` for non-geometry round-trip tests, (b) a Postgres+PostGIS test-database fixture (spun up via the same docker-compose service, or `testcontainers-python` if the planner prefers hermetic per-test-run containers) for geometry-specific and migration tests
- [ ] `backend/tests/test_models_roundtrip.py` — covers SCHM-01
- [ ] `backend/tests/test_append_only.py` — covers SCHM-02
- [ ] `backend/tests/test_status_lifecycle.py` — covers SCHM-03
- [ ] `backend/tests/test_report_geometry.py` — covers SCHM-04
- [ ] `backend/tests/test_migrations.py` — covers migration round-trip (all reqs, structural)
- [ ] Framework install: `pip install pytest pytest-asyncio` (already in STACK.md's install block, but not yet run against an actual `requirements.txt`/`requirements-dev.txt` in this repo — repo is currently empty)

**Note on SQLite fallback (D-04):** SQLite has no native PostGIS/Geometry support, so `test_models_roundtrip.py`'s Report-entity case and any geometry-touching test cannot run against SQLite — either (a) skip/xfail the geometry assertion under a SQLite fixture and only fully verify it under the Postgres+PostGIS fixture, or (b) run the entire suite only against Postgres+PostGIS in Docker and treat "SQLite acceptable for dev" (D-04) as applying to non-geometry-touching future phases' tests, not this phase's. Recommend (b) for Phase 1 specifically, since 4 of 7 entities have no geometry dependency but Report does, and splitting the fixture strategy per-test adds complexity for marginal speed benefit at this phase's small scale.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|-----------------|---------|---------------------|
| V2 Authentication | No | Phase 1 has no auth surface — no routes, no login. Deferred to Phase 7 (AUTH-01/02). |
| V3 Session Management | No | Same as above. |
| V4 Access Control | No | No API endpoints exist yet in this phase. |
| V5 Input Validation | Partial | The Pydantic schema layer mirroring these SQLAlchemy models (locked by STACK.md as the contract layer) should validate lat/lng ranges (-90..90, -180..180) and accuracy non-negativity at the Pydantic level even though this phase builds no live endpoint yet — worth encoding as model-level `field_validator`s now since the contract is being locked in this phase. `[ASSUMED — Pydantic v2 field_validator syntax stable, standard practice, not independently re-verified this session]` |
| V6 Cryptography | No | No secrets, tokens, or encrypted fields in this phase's entities. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| SQL injection via raw string-built queries | Tampering | Not applicable if all queries go through SQLAlchemy's parameterized `Mapped`/ORM query API (as designed in this research) — never string-format user input into raw SQL. Enforce via code review, not a runtime control, in this phase. |
| Malformed/out-of-range GPS coordinates accepted as valid (e.g. lat=999) | Tampering / Data Integrity | Pydantic-level range validation (V5 above) at the contract layer, even before Phase 2 wires a live endpoint — validate now so the constraint travels with the schema definition from the start. |
| PostGIS SRID mismatch (a point inserted with the wrong SRID silently "succeeds" but is geographically wrong) | Tampering (data-integrity variant) | Always construct geometry values through a single centralized helper (see Pitfall 1) that hard-codes SRID 4326 — never accept an arbitrary SRID from external input in this phase's scope. |

## Sources

### Primary (HIGH confidence)
- [GeoAlchemy2 — New ORM Declarative Mapping Style](https://geoalchemy-2.readthedocs.io/en/latest/gallery/test_orm_mapped_v2.html) — `Mapped[WKBElement]` + `mapped_column(Geometry(...))` pattern, confirmed current
- [GeoAlchemy2 — Use Alembic with GeoAlchemy 2](https://geoalchemy-2.readthedocs.io/en/stable/alembic.html) — `alembic_helpers` wiring, confirmed current
- PyPI JSON API direct queries (`pypi.org/pypi/<pkg>/json`) for sqlalchemy, geoalchemy2, alembic, asyncpg, psycopg, pydantic, fastapi — package age/release-count/classifier verification, this session
- `.planning/research/STACK.md` — already-locked stack decisions and version pins (this project's own prior research)
- `.planning/research/ARCHITECTURE.md` — already-locked architecture/anti-patterns (this project's own prior research)
- `.planning/research/PITFALLS.md` — already-locked pitfalls (this project's own prior research)

### Secondary (MEDIUM confidence)
- [Alembic GitHub Discussion #1208 — Async migration with asyncpg](https://github.com/sqlalchemy/alembic/discussions/1208) — sync/async driver split pattern for `env.py`
- [SQLAlchemy GitHub Discussion #10698 — UUID primary key generation](https://github.com/sqlalchemy/sqlalchemy/discussions/10698) — client-side vs server-side UUID default tradeoffs

### Tertiary (LOW confidence / ASSUMED)
- Reconstructed field lists for all 7 entities (see Assumptions Log A1/A4) — synthesized from REQUIREMENTS.md and PROJECT.md's Active bullets in the absence of the referenced-but-missing architecture PDF
- Repository-layer append-only pattern shape (Pattern 4) — general OOP idiom, not sourced from an external authority
- `sa.Enum` + Python `enum.Enum` syntax (Pattern 3) — stable, long-standing SQLAlchemy API, not independently re-verified via WebSearch this session (training-knowledge confidence, low risk given API stability)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified directly against PyPI this session, matching already-locked STACK.md pins with zero drift
- Architecture (repository pattern, project structure): MEDIUM-HIGH — GeoAlchemy2/Alembic wiring confirmed via official docs; repository-layer append-only enforcement is a sound but unsourced synthesis of D-08's explicit instruction
- Field-list completeness (SCHM-01's actual entity shapes): LOW — the canonical source (PROJECT.md §4 / the referenced PDF) does not exist in this repository; reconstructed field lists are a best-effort synthesis pending user/planner confirmation (see Open Question 1 — this is the most important unresolved item from this research session)
- Pitfalls: MEDIUM-HIGH — GeoAlchemy2/Alembic-specific pitfalls (2, 3) confirmed via official docs; coordinate-ordering pitfall (1) is well-known GIS domain knowledge; enum-extension pitfall (4) is standard Postgres behavior

**Research date:** 2026-09-22
**Valid until:** ~60 days (stable, mature libraries — SQLAlchemy/Alembic/GeoAlchemy2/PostGIS all have slow-moving, backward-compatible release cadences; re-verify sooner only if the missing-PDF field-list gap (Open Question 1) is resolved and materially changes the entity shapes)

---
*Phase 1 research for: RoadTwin Schema & Core Data Contracts*
*Researched: 2026-09-22*
