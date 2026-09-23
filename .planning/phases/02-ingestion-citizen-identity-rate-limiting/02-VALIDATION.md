---
phase: 2
slug: ingestion-citizen-identity-rate-limiting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-23
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Seeded from `02-RESEARCH.md`'s Validation Architecture section; task IDs below are provisional (REQ-ID keyed) until `02-*-PLAN.md` assigns final wave/task numbers — the planner should align them, not re-derive the test map from scratch. Threat Refs use ASVS categories pending the planner's `<threat_model>` block, which will assign concrete T-02-XX IDs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (backend, already configured — `pytest.ini`, `asyncio_mode = auto`); no frontend test framework exists yet |
| **Config file** | `pytest.ini` (repo root, from Phase 1) |
| **Quick run command** | `pytest backend/tests/test_reports_ingestion.py backend/tests/test_ingestion_identity.py backend/tests/test_rate_limit.py backend/tests/test_upload.py -x -q` |
| **Full suite command** | `pytest` (from repo root; `testpaths = backend/tests`) |
| **Estimated runtime** | ~15-40s (new integration tests hit Postgres directly; MinIO-backed upload test adds I/O against the docker-compose service) |

---

## Sampling Rate

- **After every task commit:** Run `pytest backend/tests/test_reports_ingestion.py backend/tests/test_ingestion_identity.py backend/tests/test_rate_limit.py backend/tests/test_upload.py -x -q` (scoped to this phase's new files)
- **After every plan wave:** Run `pytest` (full backend suite, catches regressions against Phase 1's schema/model tests)
- **Before `/gsd-verify-work`:** Full suite must be green, **plus** one manual smoke test against a real `docker-compose up` MinIO instance (not mocked) for INGT-04 — `minio` SDK behavior against a mock vs. a real server can diverge on bucket-creation idempotency and presigned-URL expiry format
- **Max feedback latency:** 40 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-TBD | TBD | TBD | INGT-01 | V5 (pending T-ID) | `POST /reports` with valid image+GPS+timestamp persists a Report and returns 201 | integration | `pytest backend/tests/test_reports_ingestion.py::test_submit_report_success -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-01 | V5 (pending T-ID) | Missing/invalid GPS is rejected with 422 — server-side Pydantic validation is sole authority (Phase 1 precedent) | unit | `pytest backend/tests/test_reports_ingestion.py::test_submit_report_invalid_gps -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-02 | V3, V6 (pending T-ID) | First request without a device-id cookie receives a signed `Set-Cookie`; subsequent request with that cookie reuses the same identity | integration | `pytest backend/tests/test_ingestion_identity.py::test_device_id_mint_and_reuse -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-02 | V6 (pending T-ID) | Tampered/invalid signed cookie is rejected and a fresh identity is minted (not a 500) | unit | `pytest backend/tests/test_ingestion_identity.py::test_tampered_cookie_remints -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-03 | — | Nth request from the same identity within the window returns 429 with `Retry-After` | integration | `pytest backend/tests/test_rate_limit.py::test_identity_rate_limit_429 -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-03 | — | Nth request from the same IP (different identities) within the window returns 429 | integration | `pytest backend/tests/test_rate_limit.py::test_ip_rate_limit_429 -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-03 | — | Second submission within the GPS-cooldown radius/window returns 429 | integration | `pytest backend/tests/test_rate_limit.py::test_gps_cooldown_429 -x` | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-04 | V12 (pending T-ID) | Successful submission's `image_path` resolves to a MinIO object retrievable via `presigned_get_object` | integration | `pytest backend/tests/test_upload.py::test_image_stored_and_retrievable -x` (requires docker-compose MinIO) | ❌ W0 | ⬜ pending |
| 02-TBD | TBD | TBD | INGT-04 | V12 (pending T-ID) | Oversized or malformed image upload is rejected (413/422), never silently truncated or stored — decompression-bomb guard active | unit | `pytest backend/tests/test_upload.py::test_reject_oversized_and_corrupt_image -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: "Threat Ref" lists the ASVS category from `02-RESEARCH.md`'s Security Domain section (V3 Session Management for the device-identity cookie's attributes, V5 Input Validation, V6 Cryptography for the `itsdangerous` HMAC signing, V12 File/Resources for upload handling). INGT-03's rate-limit bypass residual risk is accepted per CONTEXT.md and has no assigned mitigation test — see Security Domain's "Rate-limit bypass by rotating IP and clearing cookies" row.*

---

## Wave 0 Requirements

- [ ] `docker-compose.yml` MinIO service addition (RESEARCH.md Code Example §6) — **hard prerequisite**, no upload-path test can run against a real backend without it
- [ ] Alembic migration `0003_ingestion_rate_limit_tables.py` — new `submission_attempt` table (or equivalent), tested via the existing `test_migrations.py` round-trip pattern
- [ ] `backend/tests/test_reports_ingestion.py` — stubs for INGT-01
- [ ] `backend/tests/test_ingestion_identity.py` — stubs for INGT-02
- [ ] `backend/tests/test_rate_limit.py` — stubs for INGT-03
- [ ] `backend/tests/test_upload.py` — stubs for INGT-04
- [ ] `backend/tests/conftest.py` fixture additions — a test MinIO client/bucket setup, either against the real docker-compose MinIO instance gated by a `minio`-style pytest marker (analogous to the existing `postgis` marker) or a lightweight fake for pure-unit tests; decide per-test during planning

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-MinIO smoke test (not mocked) | INGT-04 | `minio` SDK behavior against a mock vs. a real server can diverge on bucket-creation idempotency and presigned-URL expiry format — automated tests alone are insufficient confidence for this phase's "permanent evidence" storage guarantee | `docker-compose up minio postgres`, submit a report with a real image via the running API, confirm the returned/stored presigned URL actually resolves the uploaded image in a browser or `curl` |
| HEIC upload support | INGT-01, INGT-04 | RESEARCH.md flags Pillow's stock build does not guarantee HEIF decoding without `pillow-heif`/libheif — open question, not yet resolved by an automated test | Upload a `.heic` file (common iPhone photo format) through the real endpoint; confirm it either processes correctly or is rejected with a clear, intentional error (not a 500) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (docker-compose MinIO service, migration, 4 test files, conftest fixtures)
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending — task IDs to be finalized against `02-*-PLAN.md` once the planner assigns wave/task numbers.
