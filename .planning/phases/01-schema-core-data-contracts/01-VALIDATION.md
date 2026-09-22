---
phase: 1
slug: schema-core-data-contracts
status: aligned-to-plan
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-22
updated: 2026-09-22
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `01-RESEARCH.md`'s Validation Architecture section; task IDs below are provisional until `01-PLAN.md` assigns final wave/task numbers — the planner should align them, not re-derive the test map from scratch.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (per `research/STACK.md`) |
| **Config file** | none yet — 01-01 T1 creates a repo-root `pytest.ini` with `asyncio_mode = auto`, `pythonpath = .`, `testpaths = backend/tests` |
| **Quick run command** | `pytest backend/tests/ -x -q` |
| **Full suite command** | `pytest backend/tests/ -v` |
| **Estimated runtime** | ~10-30s (small model set, no network calls; Postgres+PostGIS tests run against a local docker-compose service) |

---

## Sampling Rate

- **After every task commit:** Run `pytest backend/tests/ -x -q` (fast subset — SQLite-backed round-trip tests where possible)
- **After every plan wave:** Run `pytest backend/tests/ -v` (full suite, including geometry tests and migration round-trip against the real Postgres+PostGIS container)
- **Before `/gsd-verify-work`:** Full suite must be green, including the migration round-trip test and the append-only structural test
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T2 | 01 | 1 | (skeleton, RED gate) | — | End-to-end happy path exists and fails only because the app module is absent | integration | `pytest backend/tests/test_skeleton_e2e.py -q` (must exit non-zero at this point) | ❌ created in 01-01-T2 | ⬜ pending |
| 01-01-T3 | 01 | 1 | SCHM-03, SCHM-04 | V5 (input validation), T-01-01, T-01-02 | `ReportCreate` rejects lat 91 / lng 181 / negative accuracy; Report defaults to `status=unverified`; `make_point` emits longitude-first WKT | unit | `pytest backend/tests/test_report_contract.py -x` | ❌ created in 01-01-T3 | ⬜ pending |
| 01-02-T1 | 02 | 2 | (all, structural) | T-01-09 | Migration round-trip: `upgrade head` → `downgrade base` → `upgrade head` with no `compare_metadata` drift, against the live Postgres+PostGIS container | integration | `pytest backend/tests/test_migrations.py -x` | ❌ created in 01-02-T1 | ⬜ pending |
| 01-02-T1 | 02 | 2 | SCHM-04 | T-01-02 | Report requires `location`, accepts nullable `gps_accuracy_meters`; `ST_Y`/`ST_X` of the stored point match the submitted lat/lng within 1e-6 and `ST_SRID` is 4326 | integration | `pytest backend/tests/test_report_geometry.py -x` | ❌ created in 01-02-T1 | ⬜ pending |
| 01-02-T2 | 02 | 2 | SCHM-01, SCHM-04 | T-01-08 | The Plan 01 end-to-end test passes unmodified: POST returns 201 with `unverified` status, GET returns the row | integration | `pytest backend/tests/test_skeleton_e2e.py -x` | ❌ created in 01-01-T2 | ⬜ pending |
| 01-04-T3 | 04 | 3 | SCHM-01 | T-01-11 | All 7 entities persist and query back through their repositories, including FK relationships; an orphan FK raises IntegrityError | unit/integration | `pytest backend/tests/test_models_roundtrip.py -x` | ❌ created in 01-04-T3 | ⬜ pending |
| 01-04-T3 | 04 | 3 | SCHM-02 | T-01-06 | The three time-series repositories expose no attribute that could replace or remove a persisted row, across their full MRO | unit | `pytest backend/tests/test_append_only.py -x` | ❌ created in 01-04-T3 | ⬜ pending |
| 01-05-T1 | 05 | 4 | SCHM-03 | T-01-08, T-01-13 | Report and Detection default to `status=unverified`; all 4 D-06 enum values settable and DB-enforced; out-of-enum value rejected by Postgres | unit/integration | `pytest backend/tests/test_status_lifecycle.py -x` | ❌ created in 01-05-T1 | ⬜ pending |
| 01-05-T1 | 05 | 4 | SCHM-01, SCHM-02 | T-01-06 | Chain seed creates one linked row in all 7 tables; a second seed grows the 3 append-only counts instead of replacing rows; status PATCH persists | integration | `pytest backend/tests/test_skeleton_chain.py -x` | ❌ created in 01-05-T1 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: "Threat Ref" populated only for SCHM-04 (input-range validation, ASVS V5) per `01-RESEARCH.md`'s Security Domain section — this phase has no auth/session/access-control surface (no routes exist yet), so V2/V3/V4 don't apply here.*

---

## Wave 0 Requirements

Wave 0 is folded into Plan 01 (wave 1) — the repository is empty, so the test harness is built in the same plan that creates the first production module. Owning task noted per item.

- [x] *(planned)* `pytest.ini` — repo root rather than `backend/`, so `import backend.models` resolves; `asyncio_mode = auto`, `pythonpath = .`, `testpaths = backend/tests`, `postgis` marker declared — **01-01 T1**
- [x] *(planned)* `backend/requirements-dev.txt` + `pip install -r backend/requirements-dev.txt` — pytest 8, pytest-asyncio, httpx — **01-01 T1**
- [x] *(planned)* `backend/tests/conftest.py` — `postgres_dsn`, `alembic_config`, `migrated_database`, `async_engine`, `session`, `client` fixtures. Per 01-RESEARCH.md's SQLite-fallback note, option (b) is adopted: the whole Phase 1 suite runs against the docker-compose Postgres+PostGIS service rather than splitting fixtures per test — **01-01 T2**
- [x] *(planned)* `backend/tests/test_skeleton_e2e.py` — end-to-end happy path, written RED — **01-01 T2**
- [x] *(planned)* `backend/tests/test_report_contract.py` — ASVS V5 coordinate/accuracy validation + axis order — **01-01 T3**
- [x] *(planned)* `backend/tests/test_migrations.py` — migration round-trip + autogenerate drift — **01-02 T1**
- [x] *(planned)* `backend/tests/test_report_geometry.py` — covers SCHM-04 — **01-02 T1**
- [x] *(planned)* `backend/tests/test_models_roundtrip.py` — covers SCHM-01 — **01-04 T3**
- [x] *(planned)* `backend/tests/test_append_only.py` — covers SCHM-02 — **01-04 T3**
- [x] *(planned)* `backend/tests/test_status_lifecycle.py` — covers SCHM-03 — **01-05 T1**
- [x] *(planned)* `backend/tests/test_skeleton_chain.py` — SCHM-01 + SCHM-02 through the HTTP surface — **01-05 T1**

**Sampling continuity note:** the full-suite gate (`pytest backend/tests/ -v`) becomes enforceable from 01-02 T2 onward. Before that point, 01-01 T2's expected-RED state means each task's automated command is scoped to its own test file: T1 verifies via the PostGIS/`psql` and config commands, T2 asserts the RED failure for the right reason, T3 runs `test_report_contract.py`. No three consecutive tasks lack an automated check.

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification. This is a pure schema/data-contracts phase with no UI, no live API routes, and no external service integration requiring manual checks.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — every task across plans 01-01..01-05 carries an `<automated>` command
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — folded into 01-01 (greenfield repo), owning tasks recorded above
- [x] No watch-mode flags — no `--watch` appears in any verify command
- [x] Feedback latency < 30s — scoped per-file commands during plans 01/02; full suite ~10–30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** task IDs finalized against `01-01-PLAN.md` through `01-05-PLAN.md` (2026-09-22). Two test files beyond the original five were added by the planner and are tracked above: `test_report_contract.py` (ASVS V5 contract validation) and `test_skeleton_chain.py` (SCHM-01/SCHM-02 through HTTP), plus the Walking Skeleton's `test_skeleton_e2e.py`.
