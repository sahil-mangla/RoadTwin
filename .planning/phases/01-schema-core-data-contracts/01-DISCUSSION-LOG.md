# Phase 1: Schema & Core Data Contracts - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-22
**Phase:** 1-Schema & Core Data Contracts
**Areas discussed:** Repository & Environment, Entity & Schema Design (auto-mode — Claude selected recommended defaults, no user prompts)

---

## Repository & Environment

| Option | Description | Selected |
|--------|-------------|----------|
| Monorepo (backend/ + frontend/ siblings) | Single repo, matches PROJECT.md's fixed stack | ✓ |
| Separate repos | Split backend/frontend into distinct git repos | |

**User's choice:** [auto] Selected recommended default — no multi-repo signal detected in this workspace.
**Notes:** Backend module layout follows PROJECT.md's Context-section reference (`models/`, `services/{spatial,intelligence,maintenance}/`, `routes/`); Phase 1 only populates `models/` and migration scaffolding.

| Option | Description | Selected |
|--------|-------------|----------|
| pip + requirements.txt | Matches research/STACK.md install commands exactly | ✓ |
| poetry / uv | Modern dependency managers | |

**User's choice:** [auto] Selected recommended default — stays consistent with already-locked STACK.md research rather than introducing a new tool.

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres+PostGIS via docker-compose (Phase 1 only) | Redis/MinIO added later, in the phases that use them | ✓ |
| Stand up full infra (Postgres+Redis+MinIO) now | All infra up front | |

**User's choice:** [auto] Selected recommended default — keeps Phase 1 scoped to schema, avoids scope creep into Phase 2/3 concerns.

---

## Entity & Schema Design

| Option | Description | Selected |
|--------|-------------|----------|
| UUID primary keys (all entities) | Avoids exposing sequential counts publicly | ✓ |
| Auto-increment integer PKs | Simpler, but leaks counts on public-facing entities | |

**User's choice:** [auto] Selected recommended default — consistency across all 7 entities, avoids enumeration risk on Report/RoadSegment.

| Option | Description | Selected |
|--------|-------------|----------|
| Status enum: unverified → corroborated → evidence_confirmed (+ rejected) | Matches PITFALLS.md Pitfall 1; reserves rejected for v2 moderation | ✓ |
| Status enum: unverified → verified only | Simpler two-state model | |

**User's choice:** [auto] Selected recommended default — directly implements PITFALLS.md's ingestion-status-lifecycle guidance and avoids a later migration for the v2 moderation path (MODR-01).

| Option | Description | Selected |
|--------|-------------|----------|
| gps_accuracy_meters (float, nullable) alongside lat/lng | Matches browser Geolocation API semantics | ✓ |
| No accuracy field, lat/lng only | Simpler, but loses signal PITFALLS.md flags as necessary | |

**User's choice:** [auto] Selected recommended default — implements SCHM-04 and PITFALLS.md Pitfall 2 directly.

| Option | Description | Selected |
|--------|-------------|----------|
| Application-layer append-only enforcement (repository exposes create only) | Sufficient for v1, simpler | ✓ |
| Database-level trigger enforcement | Stronger guarantee, more upfront complexity | |

**User's choice:** [auto] Selected recommended default — sufficient to satisfy SCHM-02 at v1; DB-level enforcement deferred as a hardening step, not required now.

---

## Claude's Discretion

- Exact Alembic migration file naming/structure, SQLAlchemy relationship/backref naming, enum implementation details (Python `Enum` + `sa.Enum` vs CHECK constraint) — no user preference expressed, left to planner/executor.
- PostGIS `Geometry(Point, 4326)` column vs plain float lat/lng — recommended to use PostGIS geometry from Phase 1 since PostGIS is already being installed, avoiding a schema migration in Phase 4.

## Deferred Ideas

None — discussion stayed within phase scope. Redis/MinIO infra setup was considered and deliberately deferred to Phase 2/3 (not a new capability, just correctly scoped).
