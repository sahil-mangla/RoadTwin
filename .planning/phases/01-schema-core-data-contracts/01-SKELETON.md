# Walking Skeleton — RoadTwin

**Phase:** 1 (Schema & Core Data Contracts)
**Generated:** 2026-09-22
**Mode:** MVP / Walking Skeleton (`MVP_MODE=true`, `WALKING_SKELETON=true`)

## Capability Proven End-to-End

> An operator running the RoadTwin dev stack can submit a road report (latitude, longitude, GPS accuracy, description) from a browser page, and immediately see it listed back with its `unverified` status and accuracy radius — the value having travelled React → FastAPI → SQLAlchemy repository → Alembic-migrated PostGIS table and back.

This is deliberately **not** the citizen ingestion feature (no image upload, no EXIF, no identity, no rate limiting — those are INGT-01..04 in Phase 2). It is the thinnest possible proof that the seven-entity schema this phase locks is real, reachable, and wired.

A second, equally thin capability proves the rest of SCHM-01/02: the same page has a **Seed 7-entity chain** button that creates one linked row in each of the seven tables and renders live row counts, and pressing it twice increases the append-only counts rather than replacing rows.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo layout | Single repo, monorepo with sibling `backend/` and `frontend/` | D-01. No multi-repo signal; matches PROJECT.md's fixed stack. |
| Backend framework | FastAPI (>=0.115) + Uvicorn, run as `uvicorn backend.main:app` from repo root | PROJECT.md locked stack; async-native, Pydantic-integrated. |
| Backend module layout | `backend/models/`, `backend/db/`, `backend/schemas/`, `backend/core/`, `backend/routes/`, `backend/services/{spatial,intelligence,maintenance}/` | D-02 + reference spec §13. `services/` and `routes/` beyond the skeleton router are empty package stubs this phase. |
| ORM | SQLAlchemy 2.0 async (`Mapped[...]` / `mapped_column()`), `AsyncSession` over asyncpg | research/STACK.md + 01-RESEARCH.md Standard Stack. Legacy `Column()` style is prohibited. |
| Spatial layer | GeoAlchemy2 `Geometry(POINT, 4326)` on `report.location`, `Geometry(LINESTRING, 4326)` on `road_segment.geometry`, alongside the spec's plain float lat/lng columns | CONTEXT.md Claude's Discretion resolution — PostGIS from day one so Phase 4 needs no schema migration. Float columns kept because reference spec §4 names them explicitly. |
| Coordinate construction | One helper module `backend/models/geo.py` exposing `make_point(latitude, longitude)` and `make_linestring(...)`, both hard-coding SRID 4326 and emitting longitude-first WKT | 01-RESEARCH.md Pitfall 1. No call site ever orders axes by hand. |
| Primary keys | UUID v4 on all seven entities, client-side `default=uuid.uuid4` | D-05 + 01-RESEARCH.md Pattern 2 (Phase 3's arq worker needs the id before any DB round-trip). |
| Status lifecycle | One shared Postgres enum type `report_status` (`unverified`, `corroborated`, `evidence_confirmed`, `rejected`) attached to `Base.metadata`, referenced by both `report.status` and `detection.status`, default `unverified` | D-06 + 01-RESEARCH.md Pattern 3 / Anti-Pattern note. `rejected` is reserved up front for v2 MODR-01 so no near-term `ALTER TYPE` migration is needed. |
| Append-only enforcement | Application layer: `AppendOnlyRepository[T]` defines no `update`/`delete`; used exclusively by `RoadObservationRepository`, `RoadHealthRepository`, `PredictionRepository` | D-08 + 01-RESEARCH.md Pattern 4. DB triggers are the documented escalation path, not v1. |
| Database | PostgreSQL 16 + PostGIS 3.4 via `postgis/postgis:16-3.4` in root `docker-compose.yml`, service name `postgres`, database `roadtwin` | D-04. Redis and MinIO are deliberately absent — Phase 3 and Phase 2 introduce them. |
| Migrations | Alembic, config at `backend/alembic.ini` (`script_location = backend/alembic`, `prepend_sys_path = .`), always invoked from repo root as `alembic -c backend/alembic.ini ...`; `geoalchemy2.alembic_helpers` wired into both offline and online modes | 01-RESEARCH.md Pitfall 2. `CREATE EXTENSION IF NOT EXISTS postgis;` runs first in revision `0001`. |
| Driver split | `DATABASE_URL` = `postgresql+asyncpg://...` for the app; `DATABASE_URL_SYNC` = `postgresql+psycopg://...` for Alembic only | 01-RESEARCH.md Pitfall 3 — Alembic's `engine_from_config()` cannot drive asyncpg. |
| Contract layer | Pydantic v2 models in `backend/schemas/`, with lat/lng range and non-negative-accuracy validators | ASVS V5 (partial) per 01-RESEARCH.md Security Domain; contract locked now even though Phase 2 wires the real endpoint. |
| Frontend | React 19.3.0 + Vite 8.x + TypeScript, hand-authored `frontend/package.json` (no unpinned scaffolder), dev proxy `/api` → `http://localhost:8000` | D-01 + CLAUDE.md §Core Framework version pins. No Leaflet/react-leaflet yet — mapping arrives with PMAP-01 in Phase 7. |
| Dependency management | `pip` + `backend/requirements.txt` / `backend/requirements-dev.txt`; `npm` + hand-authored `frontend/package.json` | D-03. |
| Test runner | pytest 8 + pytest-asyncio, repo-root `pytest.ini` with `asyncio_mode = auto`, `pythonpath = .`, `testpaths = backend/tests` | 01-VALIDATION.md. Root-level config (rather than `backend/pytest.ini`) so `import backend.models` resolves — 01-VALIDATION.md permits either location. |
| Deployment target | None this phase. Documented local full-stack run command in `README.md` is the deliverable. | Walking Skeleton allows "documented local-run command that exercises the full stack" in place of a deploy. |

## Stack Touched in Phase 1

- [ ] Project scaffold — `docker-compose.yml`, `backend/requirements.txt`, `pytest.ini`, `frontend/package.json`, `.gitignore` (Plan 01 T1, Plan 03 T1)
- [ ] Routing — `backend/routes/skeleton.py` mounted at `/api/skeleton` by `backend/main.py` (Plan 02 T2)
- [ ] Database — real write (`POST /api/skeleton/reports` inserts a `report` row) AND real read (`GET /api/skeleton/reports` selects it back) against migrated PostGIS (Plan 02)
- [ ] UI — `frontend/src/pages/SkeletonPage.tsx` form posts to the API and renders the returned list (Plan 03 T2)
- [ ] Deployment — documented four-command local full-stack run in `README.md` (Plan 03 T2)

## Out of Scope (Deferred to Later Slices)

Explicit, so no later phase re-litigates Phase 1's minimalism:

- Image upload, object storage, EXIF GPS extraction, citizen identity, rate limiting — **Phase 2** (INGT-01..04). `report.image_path` exists as a nullable column now; Phase 2 populates it and decides its nullability.
- Citizen-identity foreign key on `report` — **Phase 2**. Deliberately not added here so Phase 1 does not pre-empt Phase 2's identity-model decision.
- YOLOv8/RDD2022 inference, arq worker, Redis — **Phase 3** (PERC-01..03). `detection.damage_type` / `detection.severity` columns exist; Phase 3 computes their values.
- DBSCAN clustering, segment reconciliation logic — **Phase 4** (SPAT-01..03). `road_segment.segment_identifier` is unique now to support stable identity later; no clustering code here.
- Evidence-score fusion, upvote/corroboration flow — **Phase 5** (EVID-01..04). `verification_score` / `contribution_weight` / `community_upvotes` columns exist; nothing computes them.
- Health-score formula, deterioration rate, forecasting, data-sufficiency gates — **Phase 6**. No `interpretation_band` column is stored — bands are a display-time reading of `health_score` (reference spec §6).
- Priority scoring, public map, authority auth/dashboard, repair workflow — **Phase 7**. `repair_status` is deliberately **not** added to any entity now; Phase 7 owns that decision (RPWF-01).
- Leaflet / react-leaflet, TanStack Query, Zustand — not installed. Frontend is one page and a `fetch` wrapper.
- Production deployment, auth on the skeleton routes, DB-level append-only triggers.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering the architectural decisions above:

- **Phase 2:** A citizen submits an image + GPS report through a real endpoint, attributed to a lightweight identity and rate-limited; images land in MinIO and `report.image_path` references them.
- **Phase 3:** A submitted image is analysed by YOLOv8 in an arq background job; each defect becomes its own `detection` row with computed severity.
- **Phase 4:** Nearby reports cluster via DBSCAN into `road_segment` rows with identity that survives re-clustering.
- **Phase 5:** Every observation gets a fused evidence score, and each segment accumulates a real `road_observation` history.
- **Phase 6:** Each segment gets a health score, deterioration rate and 30/60/90-day forecast, gated by data sufficiency.
- **Phase 7:** Segments rank into an explained priority queue behind a public map and an authenticated authority dashboard with repair workflow.

## Skeleton Retirement Criteria

`/api/skeleton/*` and `SkeletonPage.tsx` exist to prove wiring, not to ship. They are mounted only when `settings.skeleton_routes_enabled` is true. Phase 2 replaces the report-creation path with the real ingestion endpoint; at that point the skeleton report form is deleted and the chain/schema-status endpoints become dev-only diagnostics or are removed outright.
