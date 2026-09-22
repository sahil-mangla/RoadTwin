---
phase: 01-schema-core-data-contracts
plan: 04
subsystem: database
tags: [sqlalchemy, geoalchemy2, postgis, pydantic, alembic, pytest]

requires:
  - phase: 01-schema-core-data-contracts (Plan 01)
    provides: "Report ORM model, ReportRepository, BaseRepository/MutableRepository/AppendOnlyRepository hierarchy, geometry helpers, docker-compose Postgres+PostGIS"
  - phase: 01-schema-core-data-contracts (Plan 02)
    provides: "Applied Alembic migration 0001, wired env.py with geoalchemy2.alembic_helpers, migration round-trip/no-drift test pattern"
provides:
  - "Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation ORM models (backend/models/) -- all seven entities now reachable from Base.metadata"
  - "Report.detections relationship (deferred from Plan 01, added now that Detection exists)"
  - "DetectionRepository, RoadSegmentRepository, MaintenanceRecommendationRepository (mutable) and RoadObservationRepository, RoadHealthRepository, PredictionRepository (append-only) in backend/db/repository.py"
  - "12 Pydantic v2 create/read contracts for the six new entities (backend/schemas/entities.py), re-exported alongside Report's"
  - "Alembic migration 0002 applied live: road_segment, detection, road_observation, road_health, prediction, maintenance_recommendation tables, all seven FKs real, one shared report_status enum"
  - "test_models_roundtrip.py (SCHM-01) and test_append_only.py (SCHM-02) test suites"
affects: ["01-05"]

tech-stack:
  added: []
  patterns:
    - "All seven ORM models share UUIDPKMixin; only Report additionally uses TimestampedMixin (created_at) -- the other six entities' field lists (verified against reference spec §4) have no created_at column"
    - "RoadSegment.geometry (LINESTRING) is derived from four endpoint floats via make_linestring, mirroring Report.location's make_point pattern -- RoadSegmentRepository.create() supplies it when not passed explicitly"
    - "Append-only repository docstrings describe consequences of mutation in prose, deliberately without naming update/delete/remove literally, so the docstring and the structural test (test_append_only.py's FORBIDDEN_MUTATING_ATTRIBUTES list) stay independent checks on the same contract"
    - "SAVEPOINT (session.begin_nested()) wraps a deliberately-failing flush in a test, so the expected IntegrityError only rolls back that one statement, not the fixture's outer per-test transaction"

key-files:
  created:
    - backend/models/detection.py
    - backend/models/road_segment.py
    - backend/models/road_observation.py
    - backend/models/road_health.py
    - backend/models/prediction.py
    - backend/models/maintenance_recommendation.py
    - backend/schemas/entities.py
    - backend/alembic/versions/0002_remaining_entities.py
    - backend/tests/test_models_roundtrip.py
    - backend/tests/test_append_only.py
  modified:
    - backend/models/__init__.py
    - backend/models/report.py
    - backend/db/repository.py
    - backend/schemas/__init__.py

key-decisions:
  - "None of the six new entities use TimestampedMixin -- their field lists (verified against reference spec §4 exactly, per the plan's own field-list acceptance test) have no created_at column, unlike Report which explicitly carries both created_at and timestamp"
  - "Detection.status binds to the same report_status_enum Python object Report.status uses (not a new sa.Enum instance), so Postgres gets exactly one report_status type and Alembic's create_type=False on the new table's column is honest, not a workaround"

requirements-completed: [SCHM-01, SCHM-02, SCHM-03]

coverage:
  - id: D1
    description: "All seven entities exist as distinct SQLAlchemy models with UUID primary keys, reachable from Base.metadata"
    requirement: SCHM-01
    verification:
      - kind: unit
        ref: "python -c 'from backend.models import Base; ...' -> 7 tables ok"
        status: pass
      - kind: unit
        ref: "python -c '...uuid pks ok'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every entity's column set matches reference spec §4 exactly, with only the additive UUID PKs, Detection.status and Prediction.method authorised by the resolution addendum"
    requirement: SCHM-01
    verification:
      - kind: unit
        ref: "python -c '...field lists ok' (exact set-symmetric-difference check against the spec's field lists)"
        status: pass
      - kind: other
        ref: "grep -rn 'repair_status' backend/models/ | wc -l -> 0; grep -rn 'interpretation_band' backend/models/ | wc -l -> 0"
        status: pass
    human_judgment: false
  - id: D3
    description: "Detection.status shares the same Postgres enum type instance as Report.status (one shared report_status type, not two)"
    requirement: SCHM-03
    verification:
      - kind: unit
        ref: "python -c '...shared enum ok' (Detection.__table__.c.status.type is Report.__table__.c.status.type)"
        status: pass
      - kind: integration
        ref: "psql: SELECT count(*) FROM pg_type WHERE typname='report_status' -> 1"
        status: pass
    human_judgment: false
  - id: D4
    description: "The three append-only repositories (RoadObservation, RoadHealth, Prediction) expose no update/delete/remove/upsert/patch attribute anywhere in their MRO; the four mutable repositories still expose update"
    requirement: SCHM-02
    verification:
      - kind: unit
        ref: "backend/tests/test_append_only.py::test_append_only_repositories_expose_no_mutating_attribute"
        status: pass
      - kind: unit
        ref: "backend/tests/test_append_only.py::test_mutable_repositories_still_expose_update"
        status: pass
    human_judgment: false
  - id: D5
    description: "A full seven-entity chain persists and reads back through the repositories; relationship collections resolve on both sides; RoadSegment.geometry SRID is 4326"
    requirement: SCHM-01
    verification:
      - kind: integration
        ref: "backend/tests/test_models_roundtrip.py::test_seven_entity_chain_persists_and_reads_back"
        status: pass
    human_judgment: false
  - id: D6
    description: "road_segment_id foreign keys are real database constraints, not merely ORM decoration"
    requirement: SCHM-01
    verification:
      - kind: integration
        ref: "backend/tests/test_models_roundtrip.py::test_road_observation_rejects_nonexistent_segment (IntegrityError)"
        status: pass
      - kind: integration
        ref: "psql information_schema.table_constraints FOREIGN KEY count on the five child tables -> 7"
        status: pass
    human_judgment: false
  - id: D7
    description: "alembic upgrade head creates all six remaining tables live; downgrade base -> upgrade head round-trips with zero autogenerate drift"
    requirement: SCHM-01
    verification:
      - kind: integration
        ref: "alembic -c backend/alembic.ini current -> 0002 (head)"
        status: pass
      - kind: integration
        ref: "backend/tests/test_migrations.py::test_migration_head_matches_model_metadata_no_drift"
        status: pass
      - kind: other
        ref: "pytest backend/tests/ -q -> 19 passed"
        status: pass
    human_judgment: false
  - id: D8
    description: "Out-of-range values are rejected at the Pydantic contract layer (ASVS V5); status is not client-settable on Detection creation"
    requirement: SCHM-03
    verification:
      - kind: unit
        ref: "python -c '...range validation ok' (RoadHealthCreate/DetectionCreate/PredictionCreate each reject an out-of-range value)"
        status: pass
      - kind: unit
        ref: "python -c '...status not client-settable' (status absent from DetectionCreate.model_fields)"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-09-22
status: complete
---

# Phase 1 Plan 4: Detection, RoadSegment & the Four Time-Series Entities Summary

**Completed the locked seven-entity data model: Detection, RoadSegment, RoadObservation, RoadHealth, Prediction and MaintenanceRecommendation, their foreign-key relationships, their repository mutability split (three structurally append-only), 12 Pydantic contracts, and migration `0002` applied live against PostGIS with zero autogenerate drift.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-09-22
- **Tasks:** 3/3 completed
- **Files modified:** 10 created, 4 modified

## Accomplishments

- Defined all six remaining SQLAlchemy 2.0 typed declarative models with field lists matching the reference spec §4 verbatim (verified by an exact set-difference check against every entity's expected column set) -- and added the `Report.detections` relationship that Plan 01 deliberately deferred, now that both sides of `back_populates` can resolve together
- `Detection.status` binds to the *same* `report_status_enum` Python object as `Report.status`, confirmed identical by object identity (`is`), so Postgres carries exactly one `report_status` enum type
- Split the repository layer along its locked mutability contract: `DetectionRepository`/`RoadSegmentRepository`/`MaintenanceRecommendationRepository` are mutable; `RoadObservationRepository`/`RoadHealthRepository`/`PredictionRepository` add nothing beyond `AppendOnlyRepository` -- structurally, not by convention -- and `RoadSegmentRepository.create()` derives its `LINESTRING` geometry from the four endpoint floats when not supplied, mirroring `ReportRepository`
- Wrote 12 Pydantic v2 create/read contract pairs with ASVS V5 range validation (confidence/probability bounds 0-1, health scores 0-100, `horizon_days > 0`) and confirmed `status` is absent from `DetectionCreate` -- arrival status is a system decision, never a client claim
- Hand-authored and applied migration `0002` against the live docker-compose Postgres 16 + PostGIS 3.4 database: all six tables created in FK-safe order, reusing the existing `report_status` enum type (`create_type=False`), with the three longitudinal composite indexes each append-only entity needs -- verified live via table count, enum-type count, and foreign-key count queries, plus a full `downgrade base` -> `upgrade head` round trip with zero `compare_metadata` drift
- Wrote and passed `test_models_roundtrip.py` (a full seven-entity chain persisting and reading back through the repositories, both directions of every relationship, `ST_SRID` confirming 4326, and an `IntegrityError` proving the `road_segment_id` foreign key is real) and `test_append_only.py` (structurally asserting the append-only/mutable asymmetry itself, not just its current state) -- full suite now 19/19 passing

## Task Commits

1. **Task 1: Define the six remaining ORM models with their relationships** - `6eb5a60` (feat)
2. **Task 2: Split the repositories along the mutability contract and write the entity contracts** - `8af32f4` (feat)
3. **Task 3: Migrate the six remaining tables and prove persistence, relationships and append-only behaviour** - `73000d8` (feat)

## Files Created/Modified

- `backend/models/detection.py` - `Detection` ORM model, shares `report_status_enum` with `Report`
- `backend/models/road_segment.py` - `RoadSegment` ORM model, derived `LINESTRING` geometry, four `back_populates` collections
- `backend/models/road_observation.py` - `RoadObservation` (append-only), composite `(road_segment_id, observed_at)` index
- `backend/models/road_health.py` - `RoadHealth` (append-only), composite `(road_segment_id, measured_at)` index
- `backend/models/prediction.py` - `Prediction` (append-only), `method` column, composite `(road_segment_id, generated_at)` index
- `backend/models/maintenance_recommendation.py` - `MaintenanceRecommendation` ORM model
- `backend/models/__init__.py` - extended to re-export all seven models
- `backend/models/report.py` - added the previously-deferred `detections` relationship
- `backend/db/repository.py` - six new concrete repositories (3 mutable, 3 append-only)
- `backend/schemas/entities.py` - 12 Pydantic v2 create/read contracts
- `backend/schemas/__init__.py` - re-exports all 14 contracts
- `backend/alembic/versions/0002_remaining_entities.py` - migration creating the six remaining tables
- `backend/tests/test_models_roundtrip.py` - SCHM-01 persistence/relationship coverage
- `backend/tests/test_append_only.py` - SCHM-02 structural coverage

## Decisions Made

- Confirmed (via the field-list acceptance test) that none of the six new entities use `TimestampedMixin` -- only `Report` has a `created_at` column distinct from its client-reported `timestamp`; the other six entities' own timestamp-shaped fields (`observed_at`, `measured_at`, `generated_at`) are the spec's actual columns, not a second server-insert-time column.
- Kept `Detection.status` bound to the literal `report_status_enum` object imported from `backend.models.enums`, rather than constructing a second `sa.Enum(ReportStatus, ...)` -- object identity is what the plan's own acceptance test checks, and it is also what guarantees Alembic emits exactly one `CREATE TYPE` across both migrations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `interpretation_band` grep false-positive in `road_health.py`'s docstring**
- **Found during:** Task 1, running the acceptance-criteria grep gate
- **Issue:** The docstring explained *why* no persisted health-band column exists by naming the literal forbidden string `interpretation_band` in prose, tripping `grep -rn 'interpretation_band' backend/models/ | wc -l` (expected `0`) even though no such column was ever defined.
- **Fix:** Reworded the docstring to describe the same prohibition ("No column for a stored health-band label") without the literal substring.
- **Files modified:** `backend/models/road_health.py`
- **Verification:** `grep -rn --include='*.py' 'interpretation_band' backend/models/ | wc -l` returns `0`.
- **Committed in:** `6eb5a60` (Task 1 commit)

**2. [Rule 1 - Bug] `MissingGreenlet` when accessing expired ORM attributes synchronously after `session.expire_all()`**
- **Found during:** Task 3, first run of `test_models_roundtrip.py`
- **Issue:** The test originally called `session.expire_all()` then immediately passed `segment.id` (and five other `.id` attributes) as plain synchronous argument expressions into `await segment_repo.get(segment.id)`. Because `expire_all()` also expires primary-key attributes, that plain (non-awaited) attribute access tried to lazily reload through the async engine outside of any `await`, raising `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`.
- **Fix:** Captured every entity's `.id` into a local variable *before* calling `session.expire_all()`, then used only those already-resolved plain values for every subsequent repository call and assertion.
- **Files modified:** `backend/tests/test_models_roundtrip.py`
- **Verification:** `pytest backend/tests/test_models_roundtrip.py -x -q` passes.
- **Committed in:** `73000d8` (Task 3 commit)

**3. [Rule 1 - Bug] `SAWarning: transaction already deassociated from connection` after the deliberate `IntegrityError` test**
- **Found during:** Task 3, first full-suite run after the roundtrip test passed
- **Issue:** The plan's IntegrityError assertion originally ran directly against the fixture's shared per-test outer transaction. Postgres aborts a transaction after a constraint violation, so the subsequent fixture teardown's `outer_transaction.rollback()` found the transaction already deassociated from the connection, emitting a `SAWarning` (harmless for this one test, but a latent risk if a later test in the same session relied on session-scoped fixtures behaving cleanly).
- **Fix:** Wrapped the deliberately-failing `observation_repo.create(...)` call in a `session.begin_nested()` SAVEPOINT, with `pytest.raises(IntegrityError)` wrapping the whole `async with` block (not nested inside it) so the exception propagates out of the context manager and rolls back only the SAVEPOINT, leaving the fixture's outer transaction fully usable.
- **Files modified:** `backend/tests/test_models_roundtrip.py`
- **Verification:** `pytest backend/tests/ -q` -- 19/19 passing, zero warnings.
- **Committed in:** `73000d8` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (3 Rule 1 bugs — all blocking the plan's own acceptance criteria or test correctness as literally specified)
**Impact on plan:** All three fixes were necessary for the plan's own acceptance criteria to be checkable or for its tests to pass cleanly; none expand scope beyond what Task 1-3 already specified.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required. Docker Desktop must remain running for `docker compose up -d postgres`, unchanged from prior plans in this phase.

## Next Phase Readiness

Plan 05 can proceed immediately: all seven entities exist, are related, and are reachable through their repositories; `backend/models/__init__.py`'s `target_metadata` is complete; migration `0002` is applied and round-trips cleanly. No blockers.

---
*Phase: 01-schema-core-data-contracts*
*Completed: 2026-09-22*

## Self-Check: PASSED

All 10 created files confirmed present on disk (`backend/models/{detection,road_segment,road_observation,road_health,prediction,maintenance_recommendation}.py`, `backend/schemas/entities.py`, `backend/alembic/versions/0002_remaining_entities.py`, `backend/tests/{test_models_roundtrip,test_append_only}.py`). All 3 task commits (`6eb5a60`, `8af32f4`, `73000d8`) confirmed present in `git log --oneline --all`. Full test suite: 19/19 passing. `alembic current` reports `0002 (head)` against the live database. No missing items.
