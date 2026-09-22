---
phase: 01-schema-core-data-contracts
verified: 2026-09-22T14:44:09Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 1: Schema & Core Data Contracts Verification Report

**Phase Goal:** The data model exists as a locked, coherent foundation — all seven core entities persisted with append-only time-series semantics and status lifecycles, ready for every downstream phase to build on.
**Verified:** 2026-09-22T14:44:09Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All seven entities (Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation) exist as distinct, related persisted models | ✓ VERIFIED | `backend/models/{report,detection,road_segment,road_observation,road_health,prediction,maintenance_recommendation}.py` each define a distinct SQLAlchemy model with a UUID PK and FK relationships (Detection→Report, RoadObservation/RoadHealth/Prediction/MaintenanceRecommendation→RoadSegment). Confirmed live in Postgres: `\dt` on the running `roadtwin-postgres` container lists `report, detection, road_segment, road_observation, road_health, prediction, maintenance_recommendation`. Behaviorally proven end-to-end: `POST /api/skeleton/chain` against the live server returned 7 distinct UUIDs (one per entity) in a single call, and `GET /api/skeleton/schema-status` immediately after showed count=1 for all 7 entities. `test_seven_entity_chain_persists_and_reads_back` and `test_chain_seed_returns_seven_distinct_uuids` pass. |
| 2 | RoadObservation, RoadHealth, and Prediction records are append-only — each computation creates a new record rather than overwriting a prior one | ✓ VERIFIED | `backend/db/repository.py`: `AppendOnlyRepository` defines only `create`/`get`/`list` (inherited from `BaseRepository`) — no `update`/`delete` method exists on it or on `RoadObservationRepository`/`RoadHealthRepository`/`PredictionRepository`, which subclass it exclusively (`MutableRepository`, which adds `update()`, is used only by Report/Detection/RoadSegment/MaintenanceRecommendation). Structural test `test_append_only_repositories_expose_no_mutating_attribute` passes. Behavioral test `test_seeding_twice_grows_append_only_counts_again` (invokes `/api/skeleton/chain` twice and asserts RoadObservation/RoadHealth/Prediction counts increase by ≥1 each time rather than being replaced) passes against the live PostGIS database. |
| 3 | Report and Detection records carry a status field that starts at "unverified" and can transition through defined lifecycle states (e.g. unverified → corroborated → evidence-confirmed) | ✓ VERIFIED | `backend/models/enums.py` defines `ReportStatus` (unverified/corroborated/evidence_confirmed/rejected) as one shared Postgres enum bound to both `Report.status` and `Detection.status`, both defaulting to `UNVERIFIED` (enforced both at the ORM `default=` and explicitly in `Report.__init__`/observed via `Detection`'s mapped_column default). `PATCH /api/skeleton/reports/{id}/status` transitions the field. Behavioral tests pass: `test_report_defaults_to_unverified_on_arrival`, `test_detection_defaults_to_unverified_on_arrival`, `test_all_four_lifecycle_values_are_settable_and_persist`, `test_status_out_of_enum_is_rejected_at_the_database_level`, `test_status_patch_persists_and_is_reflected_on_get`. The frontend also surfaces a status badge and a transition control that calls this endpoint (`SkeletonPage.tsx` `handleStatusChange` → `updateReportStatus`). |
| 4 | A Report's location is stored with a GPS accuracy/error-radius value alongside latitude/longitude, not a bare coordinate pair | ✓ VERIFIED | `backend/models/report.py`: `gps_accuracy_meters: Mapped[float | None]` exists alongside `latitude`/`longitude` and the PostGIS `location` point column. `backend/schemas/report.py`'s `ReportCreate.gps_accuracy_meters: float | None = Field(default=None, ge=0)` rejects negative accuracy. Migration `0001_initial_report_schema.py` creates the `gps_accuracy_meters` column in the live `report` table. Behavioral tests pass: `test_negative_accuracy_raises`, `test_report_gps_accuracy_persists_and_defaults_to_none`. Frontend form collects and displays accuracy in metres (`formatAccuracy`). |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/models/report.py` | Report ORM with geometry, accuracy, status lifecycle | ✓ VERIFIED | Exists, substantive, wired (used by `ReportRepository`, `routes/skeleton.py`) |
| `backend/models/detection.py` | Detection ORM sharing report_status enum | ✓ VERIFIED | Exists, substantive, wired |
| `backend/models/road_segment.py` | RoadSegment ORM with LINESTRING geometry | ✓ VERIFIED | Exists, substantive, wired |
| `backend/models/road_observation.py` | Append-only RoadObservation ORM | ✓ VERIFIED | Exists, substantive, wired |
| `backend/models/road_health.py` | Append-only RoadHealth ORM | ✓ VERIFIED | Exists, substantive, wired |
| `backend/models/prediction.py` | Append-only Prediction ORM with recorded forecast method | ✓ VERIFIED | Exists, substantive, wired |
| `backend/models/maintenance_recommendation.py` | MaintenanceRecommendation ORM | ✓ VERIFIED | Exists, substantive, wired |
| `backend/db/repository.py` | BaseRepository/MutableRepository/AppendOnlyRepository + 7 concrete repos | ✓ VERIFIED | All 7 concrete repositories present; append-only split structurally enforced |
| `backend/alembic/versions/0001_initial_report_schema.py` + `0002_remaining_entities.py` | Migrations creating all 7 tables | ✓ VERIFIED | Both applied to live DB; `alembic_version` + all 7 entity tables present in `roadtwin-postgres` |
| `backend/routes/skeleton.py` | POST/GET reports, POST chain, GET schema-status, PATCH status | ✓ VERIFIED | All 5 endpoints present and exercised live |
| `backend/schemas/report.py`, `backend/schemas/skeleton.py` | Report + skeleton diagnostic contracts | ✓ VERIFIED | Range/format validation present and tested |
| `frontend/src/pages/SkeletonPage.tsx` | Report form, schema-status panel, chain-seed control, status transition UI | ✓ VERIFIED | All four UI elements present, wired to `api/client.ts`, builds cleanly (`tsc -b && vite build` succeeded) |
| `README.md` | Full-stack boot instructions | ✓ VERIFIED | 4-command sequence present, plus test-run instructions |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `backend/alembic/env.py` | `backend/models/__init__.py` | `target_metadata = Base.metadata` | ✓ WIRED | Confirmed via successful `alembic upgrade head` producing all model-defined tables |
| `backend/routes/skeleton.py` | `backend/db/repository.py` | Repository calls for all 7 entities | ✓ WIRED | Live `POST /chain` call created 7 rows via 7 repositories in one transaction |
| `frontend/src/pages/SkeletonPage.tsx` | `frontend/src/api/client.ts` | `createReport / listReports / seedChain / getSchemaStatus / updateReportStatus` | ✓ WIRED | All five functions imported and called from component handlers |
| `frontend/src/api/client.ts` | `backend/routes/skeleton.py` | fetch through Vite dev proxy to `/api/skeleton/*` | ✓ WIRED | Confirmed by matching URL constants and route prefix; backend responded correctly to live curl requests on the same paths |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `SkeletonPage.tsx` reports list | `reports` (useState) | `listReports()` → `GET /api/skeleton/reports` → `ReportRepository.list()` → real Postgres query | Yes | ✓ FLOWING |
| `SkeletonPage.tsx` schema-status table | `schemaStatus` (useState) | `getSchemaStatus()` → `GET /api/skeleton/schema-status` → `select(func.count())` per entity | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full backend test suite runs against live PostGIS and passes | `.venv/bin/python -m pytest backend/tests -q` (run once, against the running `roadtwin-postgres` container) | `30 passed in 2.89s` | ✓ PASS |
| Chain-seed endpoint creates one row per entity end-to-end | `curl -X POST http://127.0.0.1:8321/api/skeleton/chain` against a locally-started `uvicorn backend.main:app` | Returned 7 distinct UUIDs + `seeded_at` | ✓ PASS |
| Schema-status reflects live counts after seeding | `curl http://127.0.0.1:8321/api/skeleton/schema-status` | `{"entities":[...count:1 x7],"total_rows":7}` | ✓ PASS |
| Frontend production build succeeds with no type errors | `npm --prefix frontend run build` | `tsc -b && vite build` succeeded, produced `dist/` bundle | ✓ PASS |
| Live database contains all 7 entity tables | `docker exec roadtwin-postgres psql -U roadtwin -d roadtwin -c "\dt"` | Lists `report, detection, road_segment, road_observation, road_health, prediction, maintenance_recommendation` plus `alembic_version` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SCHM-01 | 01-01, 01-02, 01-04, 01-05 | Persist all 7 entities as distinct, related models | ✓ SATISFIED | See Truth #1 |
| SCHM-02 | 01-04, 01-05 | RoadObservation/RoadHealth/Prediction append-only | ✓ SATISFIED | See Truth #2 |
| SCHM-03 | 01-01, 01-03, 01-04, 01-05 | Report/Detection status lifecycle | ✓ SATISFIED | See Truth #3 |
| SCHM-04 | 01-01, 01-02, 01-03 | GPS accuracy alongside lat/long | ✓ SATISFIED | See Truth #4 |

No orphaned requirements: REQUIREMENTS.md maps only SCHM-01..04 to Phase 1, and all four appear in at least one plan's `requirements` frontmatter field.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX`, `TODO|HACK|PLACEHOLDER`, and common stub-return patterns (`return null|return {}|return []|=> {}`) across `backend/` and `frontend/src/` returned zero matches.

### Code Review Findings (01-REVIEW.md) Disposition

- **CR-01 (Critical — disabled form validation let empty lat/long silently persist (0,0)):** Fixed post-review by the orchestrator directly, commit `276938c`. Verified: `SkeletonPage.tsx`'s `handleSubmit` now rejects empty/non-finite latitude or longitude before calling `createReport`, setting a user-visible error instead. Confirmed via diff and current file contents.
- **WR-01 (`backend/schemas/entities.py` dead code)**, **WR-02 (`ReportCreate.image_path` unvalidated)**, **WR-03 (missing bbox cross-field validation)**, **WR-04 (`MutableRepository.update()` silent no-op on typo)**, **IN-01/IN-02/IN-03**: All open, non-blocking. None of these affect the four SCHM success criteria — WR-01/WR-03 concern Pydantic contracts for entities not yet exercised by any route (explicitly deferred to Phase 2+ ingestion); WR-02 is a forward-looking hardening item ahead of Phase 2's upload pipeline; WR-04 and the IN items are hygiene/defense-in-depth items. Per the task's explicit instruction, these are not treated as phase-goal blockers.

### Human Verification Required

None. All four success criteria were verified through direct codebase inspection, a live-database schema check, and a real (non-mocked) test run plus live HTTP calls against a locally started server — no visual, real-time, or external-service-dependent behavior remains to check for this phase's scope.

### Gaps Summary

No gaps. All four ROADMAP.md success criteria for Phase 1 are verified against the live, running system (not just static code or SUMMARY claims): the seven-entity schema is migrated into a real PostgreSQL/PostGIS database, the append-only enforcement is both structurally absent (no mutating methods) and behaviorally proven (repeated seeding grows counts), the status lifecycle defaults and transitions correctly through the shared Postgres enum, and GPS accuracy is a first-class validated column alongside latitude/longitude. The one Critical code-review finding (CR-01) was already fixed and verified fixed in a follow-up commit prior to this verification pass. Remaining code-review Warnings/Info items are legitimate hardening backlog for later phases, not gaps in this phase's stated goal.

---

_Verified: 2026-09-22T14:44:09Z_
_Verifier: Claude (gsd-verifier)_
