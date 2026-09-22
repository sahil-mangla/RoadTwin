# Phase 1: Schema & Core Data Contracts - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the locked, coherent data-model foundation for RoadTwin: all seven core entities (Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation) as persisted SQLAlchemy/Pydantic models with a working Alembic migration baseline, PostGIS enabled, append-only time-series semantics on RoadObservation/RoadHealth/Prediction, a status lifecycle on Report/Detection, and GPS accuracy metadata captured on Report. No intelligence-layer logic (clustering, evidence fusion, scoring, forecasting) is implemented here — this phase only locks the contracts those later phases will build on. No ingestion API, no ML inference, no frontend.

</domain>

<decisions>
## Implementation Decisions

This is an infrastructure/schema phase with few user-facing gray areas — most implementation questions were already answered by prior research (STACK.md, ARCHITECTURE.md, PITFALLS.md). Auto-mode resolved the remaining technical gray areas using the research's recommended defaults; logged below for auditability.

### Repository & Environment

- **D-01:** Single git repo (this one), monorepo layout with sibling `backend/` (FastAPI) and `frontend/` (React/Vite) directories — no separate repos. *(recommended default — matches PROJECT.md's fixed stack, no multi-repo signal detected)*
- **D-02:** Backend module layout follows the layout already referenced in PROJECT.md's Context section: `backend/models/`, `backend/services/{spatial,intelligence,maintenance}/`, `backend/routes/`. Phase 1 only populates `models/` plus Alembic migration scaffolding — `services/` and `routes/` are created empty/stubbed as needed by later phases, not built out now.
- **D-03:** Python dependency management via plain `pip` + `requirements.txt`, exactly matching the install commands already documented in `research/STACK.md` — no poetry/uv switch, to avoid diverging from already-locked research.
- **D-04:** Local dev/test database: SQLite acceptable for fast unit tests only (per PROJECT.md constraint). Actual dev target is PostgreSQL 16 + PostGIS 3.4 via `docker-compose` (Postgres only in this phase — Redis/MinIO are introduced later in the phases that actually use them, Phase 3 and Phase 2 respectively, to keep this phase scoped to schema).

### Entity & Schema Design

- **D-05:** Primary keys: UUID (v4) on all seven entities. *(recommended default — avoids exposing sequential counts on public-facing entities like Report/RoadSegment; consistent across the whole model rather than mixing UUID/int)*
- **D-06:** Report/Detection status lifecycle enum: `unverified → corroborated → evidence_confirmed`, plus `rejected` (reserved for the v2 moderation-flag path, REQUIREMENTS.md MODR-01, so the column doesn't need a later migration). New records default to `unverified`. This directly implements PITFALLS.md's Pitfall 1 (unverified reports must not be treated as fact at ingestion).
- **D-07:** Report GPS fields: `latitude`, `longitude` (both required), plus `gps_accuracy_meters` (float, nullable) — following the browser Geolocation API's `coords.accuracy` semantics (meters, radius). Implements SCHM-04 and PITFALLS.md's Pitfall 2 (GPS noise must be captured as metadata, not ignored).
- **D-08:** Append-only enforcement for RoadObservation, RoadHealth, and Prediction is done at the application/repository layer for v1 (these tables expose only `create`, never `update`, in the data-access layer) rather than a database-level trigger. *(recommended default — DB-level enforcement is a reasonable hardening step but not required to satisfy SCHM-02 at v1; revisit only if application-layer discipline proves insufficient)*
- **D-09:** All seven entities match the field lists already specified in PROJECT.md §4 (Data Model) verbatim — Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation. No new fields invented beyond what SCHM-01..04 and the research require (e.g., D-05 UUID PKs, D-06 status enum, D-07 GPS accuracy are additive to the locked field lists, not replacements).

### Claude's Discretion

- Exact Alembic migration file naming/structure, exact SQLAlchemy relationship/backref naming, and exact enum implementation (Python `Enum` + `sa.Enum` vs string column with CHECK constraint) are left to the planner/executor to decide using SQLAlchemy 2.0 best practice — no user preference expressed.
- GeoAlchemy2 column types for lat/lng vs a PostGIS `Geometry(POINT, 4326)` column: research (STACK.md) notes PostGIS is not strictly required on day one but should be installed now so the schema migration path is trivial later — planner should default to a PostGIS `Geometry(Point, 4326)` column from the start (since Phase 1 already stands up PostGIS) rather than plain float lat/lng columns, to avoid a schema migration in Phase 4.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope & data model
- `.planning/reference/RoadTwin-Architecture-Input-Spec.md` §4 (Data Model) — **canonical, verbatim field lists for all 7 entities** (Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation). Corrects an earlier dangling reference: PROJECT.md originally cited a source PDF that was never committed to the repo — this file is the transcribed, git-tracked replacement and is now the actual source of truth. §13 also has a suggested `backend/` module layout (note: it omits a model file for MaintenanceRecommendation — add `models/maintenance_recommendation.py` to cover all 7 entities).
- `.planning/PROJECT.md` — project-level context and constraints; §Context points to the reference spec above
- `.planning/REQUIREMENTS.md` — SCHM-01..04 (this phase's requirements), plus INGT/PERC/SPAT/EVID/HLTH downstream requirements that depend on this phase's schema decisions
- `.planning/ROADMAP.md` Phase 1 section — goal and success criteria this phase must satisfy

### Research (already-locked technical decisions for this phase)
- `.planning/research/STACK.md` §"Database & ORM" — SQLAlchemy 2.0 async + GeoAlchemy2 + Alembic + asyncpg/psycopg version pins and install commands
- `.planning/research/ARCHITECTURE.md` — Anti-Pattern 4 (append-only time-series tables) and the overall entity data-flow chain (Report→Detection→RoadObservation→RoadSegment→RoadHealth→Prediction→MaintenanceRecommendation)
- `.planning/research/PITFALLS.md` — Pitfall 1 (unverified reports treated as fact — status lifecycle) and Pitfall 2 (GPS noise/accuracy) — both directly addressed by this phase's schema

No other external specs/ADRs exist yet for this project.

</canonical_refs>

<code_context>
## Existing Code Insights

No existing code in this repository — this is the first implementation phase of a greenfield project. Nothing to reuse or integrate with yet; this phase establishes the first code.

</code_context>

<specifics>
## Specific Ideas

No specific implementation examples given beyond what's captured in PROJECT.md's Data Model section (§4) and the research files above — open to standard SQLAlchemy 2.0/Alembic/FastAPI conventions for anything not explicitly decided.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Redis/MinIO infra setup was considered for this phase but deliberately deferred to Phase 2/3 per D-04, to keep Phase 1 scoped to schema only, not scope creep — noted here for traceability, not because it's a new capability.)

</deferred>

---

*Phase: 1-Schema & Core Data Contracts*
*Context gathered: 2026-09-22*
