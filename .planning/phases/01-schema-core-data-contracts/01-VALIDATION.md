---
phase: 1
slug: schema-core-data-contracts
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-22
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `01-RESEARCH.md`'s Validation Architecture section; task IDs below are provisional until `01-PLAN.md` assigns final wave/task numbers — the planner should align them, not re-derive the test map from scratch.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (per `research/STACK.md`) |
| **Config file** | none yet — Wave 0 creates `backend/pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` with `asyncio_mode = auto` |
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
| 01-TBD | 01 | 0 | SCHM-01 | — | All 7 entities persist and query back, including FK relationships | unit/integration | `pytest backend/tests/test_models_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| 01-TBD | 01 | 0 | SCHM-02 | — | RoadObservation/RoadHealth/Prediction repositories expose no `update`/`delete` | unit | `pytest backend/tests/test_append_only.py -x` | ❌ W0 | ⬜ pending |
| 01-TBD | 01 | 0 | SCHM-03 | — | Report/Detection default to `status=unverified`; all 4 enum values settable | unit | `pytest backend/tests/test_status_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 01-TBD | 01 | 0 | SCHM-04 | V5 (input validation) | Report requires `location`, accepts nullable `gps_accuracy_meters`; round-tripped point matches input within float tolerance | unit/integration | `pytest backend/tests/test_report_geometry.py -x` | ❌ W0 | ⬜ pending |
| 01-TBD | 01 | 0 | (all, structural) | — | Migration round-trip: `upgrade head` → `downgrade base` → `upgrade head` with no drift | integration | `pytest backend/tests/test_migrations.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: "Threat Ref" populated only for SCHM-04 (input-range validation, ASVS V5) per `01-RESEARCH.md`'s Security Domain section — this phase has no auth/session/access-control surface (no routes exist yet), so V2/V3/V4 don't apply here.*

---

## Wave 0 Requirements

- [ ] `backend/pytest.ini` (or `pyproject.toml` pytest config) — `asyncio_mode = auto`, test discovery paths
- [ ] `backend/tests/conftest.py` — fixtures: (a) SQLite in-memory `AsyncSession` for non-geometry round-trip tests, (b) Postgres+PostGIS test-database fixture (via the same docker-compose service) for geometry-specific and migration tests
- [ ] `backend/tests/test_models_roundtrip.py` — covers SCHM-01
- [ ] `backend/tests/test_append_only.py` — covers SCHM-02
- [ ] `backend/tests/test_status_lifecycle.py` — covers SCHM-03
- [ ] `backend/tests/test_report_geometry.py` — covers SCHM-04
- [ ] `backend/tests/test_migrations.py` — covers migration round-trip (all requirements, structural)
- [ ] `pip install pytest pytest-asyncio` — framework install (repo is currently empty, no `requirements.txt` yet)

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification. This is a pure schema/data-contracts phase with no UI, no live API routes, and no external service integration requiring manual checks.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending — task IDs finalized once `01-PLAN.md` is written by the planner.
