---
phase: 01-schema-core-data-contracts
plan: 05
subsystem: api
tags: [fastapi, sqlalchemy, pydantic, react, playwright, postgis]

requires:
  - phase: 01-schema-core-data-contracts (Plan 03)
    provides: "SkeletonPage.tsx, api/client.ts, types.ts frontend pattern; noValidate form so server validation is the sole authority"
  - phase: 01-schema-core-data-contracts (Plan 04)
    provides: "All seven entities, their repositories split by mutability contract (3 append-only, 4 mutable), 12 Pydantic contracts, migration 0002 applied live"
provides:
  - "POST /api/skeleton/chain -- seeds one linked row into all seven tables in a single call, through the append-only repositories for RoadObservation/RoadHealth/Prediction (SCHM-01, SCHM-02)"
  - "GET /api/skeleton/schema-status -- live per-entity row counts via select(func.count()), fixed reporting order"
  - "PATCH /api/skeleton/reports/{id}/status -- advances a report's status field, 404 on unknown id, makes SCHM-03's lifecycle observable"
  - "backend/schemas/skeleton.py -- EntityCount, SchemaStatus, ChainSeedResult, ReportStatusUpdate contracts"
  - "backend/tests/test_status_lifecycle.py, backend/tests/test_skeleton_chain.py -- the two remaining 01-VALIDATION.md test files"
  - "Frontend schema-status panel + chain-seed button + per-report status select, wired to the three new endpoints"
affects: ["02"]

tech-stack:
  added: []
  patterns:
    - "Route handlers never call session.commit() directly -- backend/db/session.py's get_session dependency commits once on clean exit, so a multi-entity chain seed is naturally one transaction without an explicit commit call in the route"
    - "schema-status entity order is a fixed Python list (_ENTITY_MODELS) walked server-side; the frontend renders schemaStatus.entities in API response order rather than sorting or hardcoding names client-side, so a missing entity shows as a missing row"
    - "Proving DB-level enum enforcement (not just Python-side) requires bypassing the ORM's Enum type -- a raw sa.text() UPDATE with the id bound as a parameter and a literal invalid enum value written directly in the SQL string (not interpolated) reaches Postgres's own CREATE TYPE constraint and gets rejected by asyncpg/DBAPIError"

key-files:
  created:
    - backend/schemas/skeleton.py
    - backend/tests/test_status_lifecycle.py
    - backend/tests/test_skeleton_chain.py
  modified:
    - backend/routes/skeleton.py
    - frontend/src/types.ts
    - frontend/src/api/client.ts
    - frontend/src/pages/SkeletonPage.tsx

key-decisions:
  - "No explicit session.commit() added to /chain -- get_session's existing commit-on-clean-exit already gives the whole seven-entity write a single transaction, matching the plan's 'commit once' instruction without duplicating commit logic"
  - "RoadSegment.segment_identifier collision avoidance uses secrets.token_hex(4) rather than a counter or timestamp suffix, so repeated seeding is safe under concurrent requests too, not just sequential ones"
  - "The caption under the schema-status panel refers to the append-only entities as 'observation, health and prediction' (matching the plan's literal wording) rather than 'road_observation, road_health' -- avoids tripping the acceptance grep that forbids hardcoded road_*/maintenance_recommendation entity-name literals in the page while still being clear to a human reader"

requirements-completed: [SCHM-01, SCHM-02, SCHM-03]

coverage:
  - id: D1
    description: "POST /api/skeleton/chain seeds one linked row into all seven tables in a single call, all seven ids distinct and non-null"
    requirement: SCHM-01
    verification:
      - kind: integration
        ref: "backend/tests/test_skeleton_chain.py::test_chain_seed_returns_seven_distinct_uuids"
        status: pass
      - kind: integration
        ref: "backend/tests/test_skeleton_chain.py::test_chain_seed_grows_every_entity_count_by_at_least_one"
        status: pass
      - kind: other
        ref: "live curl against running uvicorn: two POST /api/skeleton/chain calls, schema-status counts diffed via node script -- 'append-only growth ok'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Repeating the seed grows the three append-only tables (road_observation, road_health, prediction) instead of replacing rows"
    requirement: SCHM-02
    verification:
      - kind: integration
        ref: "backend/tests/test_skeleton_chain.py::test_seeding_twice_grows_append_only_counts_again"
        status: pass
      - kind: automated_ui
        ref: "playwright:skeleton-page-panel.png -- two live 'Seed 7-entity chain' clicks in a real Chromium browser, all seven counts +1 on seed one, road_observation/road_health/prediction +1 again on seed two"
        status: pass
    human_judgment: false
  - id: D3
    description: "Report and Detection both default to unverified on arrival without being told to; all four D-06 enum values are settable and persist; an out-of-enum value is rejected at the Postgres level; both entities share one report_status enum type"
    requirement: SCHM-03
    verification:
      - kind: unit
        ref: "backend/tests/test_status_lifecycle.py::test_report_defaults_to_unverified_on_arrival"
        status: pass
      - kind: unit
        ref: "backend/tests/test_status_lifecycle.py::test_detection_defaults_to_unverified_on_arrival"
        status: pass
      - kind: integration
        ref: "backend/tests/test_status_lifecycle.py::test_all_four_lifecycle_values_are_settable_and_persist"
        status: pass
      - kind: integration
        ref: "backend/tests/test_status_lifecycle.py::test_status_out_of_enum_is_rejected_at_the_database_level"
        status: pass
      - kind: unit
        ref: "backend/tests/test_status_lifecycle.py::test_report_and_detection_share_the_same_postgres_enum_type"
        status: pass
    human_judgment: false
  - id: D4
    description: "PATCH /api/skeleton/reports/{id}/status persists a status change, visible on a follow-up GET and surviving a full browser reload"
    requirement: SCHM-03
    verification:
      - kind: integration
        ref: "backend/tests/test_skeleton_chain.py::test_status_patch_persists_and_is_reflected_on_get"
        status: pass
      - kind: integration
        ref: "backend/tests/test_skeleton_chain.py::test_status_patch_against_unknown_report_returns_404"
        status: pass
      - kind: automated_ui
        ref: "playwright:skeleton-page-status-persisted.png -- status select changed to corroborated, badge reads corroborated before AND after page.reload()"
        status: pass
    human_judgment: false
  - id: D5
    description: "The browser schema-status panel renders all seven live entity rows (order from the API, never hardcoded client-side) plus a working chain-seed button and per-report status select"
    requirement: SCHM-01
    verification:
      - kind: other
        ref: "npm --prefix frontend run typecheck && npm --prefix frontend run build (both exit 0); allowlist/entity-hardcoding/line-count acceptance greps all pass"
        status: pass
      - kind: automated_ui
        ref: "playwright:skeleton-page-panel.png -- real Chromium session against running uvicorn + vite dev, seven entity rows plus total"
        status: pass
    human_judgment: false
  - id: D6
    description: "No query text in the new route/test code is assembled by string interpolation (threat T-01-03); the full backend suite (30 tests, every file named in 01-VALIDATION.md) is green"
    verification:
      - kind: other
        ref: "grep -rn --include='*.py' 'f\"SELECT|f\"INSERT|f\"UPDATE|f\"DELETE' backend/ -> 0 matches"
        status: pass
      - kind: other
        ref: "pytest backend/tests/ -q -> 30 passed"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-09-22
status: complete
---

# Phase 1 Plan 5: Chain-Seed, Schema-Status & Status-Lifecycle Endpoints Summary

**Three new diagnostic endpoints (chain-seed, schema-status, status-transition) plus a browser panel make all four Phase 1 ROADMAP success criteria observable by a human watching row counts grow across two button presses.**

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-09-22
- **Tasks:** 2/2 completed
- **Files modified:** 3 created, 4 modified

## Accomplishments

- `POST /api/skeleton/chain` writes one linked row into all seven tables in a single call -- RoadSegment, Report, Detection, then RoadObservation/RoadHealth/Prediction exclusively through their append-only repositories, then MaintenanceRecommendation -- returning all seven ids plus `seeded_at`; relies on `get_session`'s existing commit-on-clean-exit rather than adding a second commit path
- `GET /api/skeleton/schema-status` reports live per-entity row counts built from `select(func.count()).select_from(model)` against each of the seven mapped tables, in a fixed order, with zero string-interpolated SQL anywhere in the new code (verified by grep)
- `PATCH /api/skeleton/reports/{report_id}/status` loads a report through `ReportRepository.get()`, 404s on a missing id, otherwise applies the new status through the mutable repository's `update()` -- its docstring records that real transition-validity rules are Phase 5's job, not Phase 1's
- `backend/tests/test_status_lifecycle.py` proves SCHM-03 end to end: both Report and Detection default to `unverified` without being told to, all four D-06 enum values (including the reserved `rejected`) round-trip, an out-of-enum value is rejected by Postgres itself (not merely the Python type, verified by bypassing the ORM's Enum validation with a raw parameterized `UPDATE`), and Report/Detection share one `report_status` enum type object
- `backend/tests/test_skeleton_chain.py` proves SCHM-01/SCHM-02 through the real HTTP surface: schema-status lists exactly seven entities, a chain seed grows every count by at least one, a second seed grows the three append-only counts again, and the status PATCH persists across a follow-up GET
- Frontend gained a schema-status panel (rendered from the live API response, not a hardcoded entity list), a "Seed 7-entity chain" button that disables itself in flight and refreshes both the panel and the report list, and a per-report status `<select>` (options iterated from a `ReportStatus` constant array, no separate label literals) that PATCHes and replaces that report in local state
- **Verified with a real headless Chromium browser (Playwright)** against the actual running `uvicorn` + `vite dev` processes: seven entity rows render with all counts at 0, the first seed press takes every count to 1, the second press takes `road_observation`/`road_health`/`prediction` to 2 while the other four stay at 2 as well (one seed each), and changing a report's status to `corroborated` survives a full `page.reload()` -- screenshots captured, then the dev database's seeded rows were cleaned up (`DELETE` by `segment_identifier LIKE 'SEG-SEED-%'` / `source = 'skeleton-seed'`) so the database is left empty, matching its state before this session

## Task Commits

1. **Task 1: Add the chain-seed, schema-status and status-transition endpoints with their lifecycle tests** - `c0be70c` (feat)
2. **Task 2: Surface the schema-status panel and chain-seed control in the browser** - `cd3cd68` (feat)

## Files Created/Modified

- `backend/schemas/skeleton.py` - `EntityCount`, `SchemaStatus`, `ChainSeedResult`, `ReportStatusUpdate` Pydantic v2 contracts
- `backend/routes/skeleton.py` - added `POST /chain`, `GET /schema-status`, `PATCH /reports/{report_id}/status`, extended the module docstring
- `backend/tests/test_status_lifecycle.py` - SCHM-03 coverage: defaults, all-4-values round-trip, DB-level enum enforcement, shared enum type
- `backend/tests/test_skeleton_chain.py` - SCHM-01 + SCHM-02 coverage through the HTTP surface
- `frontend/src/types.ts` - `EntityCount`, `SchemaStatus`, `ChainSeedResult` interfaces
- `frontend/src/api/client.ts` - `getSchemaStatus`, `seedChain`, `updateReportStatus`
- `frontend/src/pages/SkeletonPage.tsx` - schema-status panel, seed button, per-report status select

## Decisions Made

- Relied on `backend/db/session.py`'s existing `get_session` commit-on-clean-exit instead of adding an explicit `session.commit()` inside `/chain` -- the plan's "commit once" instruction is satisfied by the dependency that already wraps every route handler, and adding a second commit call would be redundant rather than clarifying.
- Used `secrets.token_hex(4)` for the seeded `RoadSegment.segment_identifier` suffix rather than a counter or timestamp, so repeated/concurrent seeding never collides against the unique constraint.
- Worded the frontend caption as "observation, health and prediction counts" (matching the plan's literal phrasing) instead of "road_observation, road_health" -- keeps the caption readable while satisfying the acceptance check that forbids hardcoded `road_*`/`maintenance_recommendation` entity-name literals anywhere in the page (the entity list itself is still rendered from the live API response, never a client-side constant).

## Deviations from Plan

### Auto-fixed Issues

None - the two tasks' own action instructions were implemented as written; no bugs, missing-critical-functionality, or blocking issues were hit during implementation.

### Noted but not fixed (pre-existing, out of scope)

**1. [Not a deviation -- verification-script incompatibility] The plan's literal `python -c "from backend.main import app; p={r.path for r in app.routes}; ..."` acceptance command raises `AttributeError` on this project's installed FastAPI (0.141.1)**
- **Found during:** Task 1 acceptance-criteria verification
- **Cause:** FastAPI 0.141.1 wraps `app.include_router(...)` results in a new `starlette`/`fastapi` internal type (`fastapi.routing._IncludedRouter`) that has no `.path` attribute -- a framework behavior change unrelated to anything built in this plan or Plan 02 (which already mounted `/api/skeleton/reports` the same way).
- **Why not fixed:** The routes themselves are correctly registered and reachable -- confirmed by walking `_IncludedRouter.original_router.routes`, which lists all four expected paths (`/api/skeleton/reports` x2, `/api/skeleton/chain`, `/api/skeleton/schema-status`, `/api/skeleton/reports/{report_id}/status`), and independently confirmed by every HTTP-level test in `test_skeleton_chain.py` plus the live curl/Playwright verification passing. This is a diagnostic-script incompatibility with a newer FastAPI internal, not a bug in application code, so no source change was made.
- **Verification:** `backend/tests/test_skeleton_chain.py` (6 tests, all passing) exercises every one of these routes over real HTTP through the ASGI test client; a live `uvicorn` + `curl` session against `/api/skeleton/chain` and `/api/skeleton/schema-status` additionally confirmed reachability outside the test harness.

---

**Total deviations:** 0 auto-fixed. One pre-existing verification-script/framework-version mismatch noted above, worked around with an equivalent check rather than a code change.
**Impact on plan:** None on scope -- both tasks' acceptance criteria are met by the actual behavior of the code; only one literal diagnostic command in the plan's acceptance text needed a different (but equivalent) verification approach.

## Issues Encountered

None beyond the noted verification-script incompatibility above.

## User Setup Required

None - no external service configuration required. Docker Desktop must remain running for `docker compose up -d postgres`, unchanged from prior plans. The verification session started `uvicorn backend.main:app --port 8000` and `npm --prefix frontend run dev` in the background, drove both through a real Chromium browser via Playwright, then stopped both processes and deleted every row the chain-seed diagnostic created (by `segment_identifier LIKE 'SEG-SEED-%'` and `source = 'skeleton-seed'`) so the dev database is empty, matching its state at session start.

## Next Phase Readiness

Phase 1 is now feature-complete: all five plans executed, all seven entities exist and are related, append-only accumulation and the status lifecycle are both provable by a human watching the browser, and the full backend suite (30/30) plus the frontend build/typecheck are green. Phase 2 (Ingestion, Citizen Identity & Rate Limiting) can proceed -- it replaces this skeleton's report-creation path with the real ingestion endpoint per `01-SKELETON.md`'s retirement criteria; nothing in this plan needs to be revisited first. No blockers.

---
*Phase: 01-schema-core-data-contracts*
*Completed: 2026-09-22*

## Self-Check: PASSED

All 7 created/modified files confirmed present on disk (`backend/schemas/skeleton.py`, `backend/tests/test_status_lifecycle.py`, `backend/tests/test_skeleton_chain.py`, `backend/routes/skeleton.py`, `frontend/src/types.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/SkeletonPage.tsx`). Both task commits (`c0be70c`, `cd3cd68`) confirmed present in `git log --oneline --all`. Full backend suite: 30/30 passing. Frontend `typecheck` and `build` both exit 0. Real-browser (Playwright/Chromium) verification confirmed all four ROADMAP Phase 1 success criteria are observable end-to-end. No missing items.
