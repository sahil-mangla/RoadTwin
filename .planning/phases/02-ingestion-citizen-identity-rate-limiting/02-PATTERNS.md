# Phase 2: Ingestion, Citizen Identity & Rate Limiting - Pattern Map

**Mapped:** 2026-09-23
**Files analyzed:** 15
**Analogs found:** 13 / 15

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/routes/reports.py` | route/controller | request-response | `backend/routes/skeleton.py` | exact (same domain, real citizen version) |
| `backend/services/ingestion/__init__.py` | package init | — | `backend/services/spatial/__init__.py` | exact |
| `backend/services/ingestion/identity.py` | service/utility | request-response (cookie mint/verify) | none (novel) | no analog — RESEARCH.md Pattern 1 is the reference |
| `backend/services/ingestion/rate_limit.py` | service | CRUD (counter reads) + request-response guard | `backend/db/repository.py` (query style) | role-match |
| `backend/services/ingestion/upload.py` | service/utility | file-I/O | none (novel — first MinIO usage) | no analog — RESEARCH.md Pattern 3/4 is the reference |
| `backend/models/rate_limit.py` | model | CRUD | `backend/models/report.py`, `backend/models/base.py` | exact (mixins, style) |
| `backend/db/repository.py` (extend) | repository | CRUD | itself — extend with `SubmissionAttemptRepository` following `MutableRepository`/`AppendOnlyRepository` split | exact |
| `backend/core/config.py` (extend) | config | — | itself — extend `Settings` | exact |
| `backend/main.py` (extend) | app bootstrap | — | itself — extend router mounting + MinIO bucket bootstrap | exact |
| `backend/schemas/report.py` (extend, maybe) | model/schema | request-response validation | itself — `ReportCreate`/`ReportRead` | exact |
| `backend/alembic/versions/0003_ingestion_rate_limit_tables.py` | migration | CRUD (DDL) | `backend/alembic/versions/0002_remaining_entities.py` | exact |
| `backend/tests/test_reports_ingestion.py` | test | request-response | `backend/tests/test_skeleton_e2e.py`, `backend/tests/test_report_contract.py` | exact |
| `backend/tests/test_ingestion_identity.py` | test | request-response | `backend/tests/test_skeleton_e2e.py` (client fixture usage) | role-match |
| `backend/tests/test_rate_limit.py` | test | request-response | `backend/tests/test_skeleton_e2e.py` | role-match |
| `backend/tests/test_upload.py` | test | file-I/O | `backend/tests/test_migrations.py` (skip-if-service-unreachable pattern) | partial-match |
| `frontend/src/pages/ReportSubmitPage.tsx` | component/page | request-response | `frontend/src/pages/SkeletonPage.tsx` | exact |
| `frontend/src/components/LocationPicker.tsx` | component | event-driven (map interaction) | none (first Leaflet component) | no analog — RESEARCH.md Code Example §1 is the reference |
| `frontend/src/api/client.ts` (extend) | service/utility | request-response | itself — extend with `createReportWithImage()`, `getReportImageUrl()` | exact |
| `frontend/src/types.ts` (extend) | model/types | — | itself — extend with multipart payload shape | exact |
| `docker-compose.yml` (extend) | config | — | existing `postgres` service block | exact |

## Pattern Assignments

### `backend/routes/reports.py` (route, request-response)

**Analog:** `backend/routes/skeleton.py` (lines 1-92)

**Imports pattern:**
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import ReportRepository
from backend.db.session import get_session
from backend.schemas.report import ReportCreate, ReportRead
```
Also add: `Form`, `UploadFile`, `Request`, `Cookie`, `Response` from `fastapi`, and the three new `backend.services.ingestion.*` modules (see RESEARCH.md Code Example §3 for the full composed route — copy that shape directly, it already matches this codebase's conventions).

**Router declaration pattern** (skeleton.py line 54):
```python
router = APIRouter(prefix="/api/skeleton", tags=["skeleton"])
```
Use `router = APIRouter(prefix="/reports", tags=["reports"])` for the new file (per RESEARCH.md's Code Example §3 — note skeleton.py's prefix is `/api/skeleton`, but RESEARCH.md's example and ARCHITECTURE.md's suggested layout use a plain `/reports` prefix; confirm final prefix against `backend/main.py`'s existing router-mounting convention and any Vite proxy config before finalizing, since skeleton routes are proxied under `/api/*`).

**Core CRUD/create pattern** (skeleton.py lines 71-84):
```python
@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate, session: AsyncSession = Depends(get_session)
) -> ReportRead:
    fields = payload.model_dump()
    if fields.get("timestamp") is None:
        fields["timestamp"] = dt.datetime.now(dt.timezone.utc)

    report = await ReportRepository(session).create(**fields)
    return ReportRead.model_validate(report)
```
Copy this exact shape (server sets `status`/`timestamp` defaults; `ReportRepository.create()` auto-derives the PostGIS `location` column — see repository.py below) but insert the identity dependency, rate-limit guard, and upload validation/MinIO write *before* the repository call, exactly as RESEARCH.md's Code Example §3 shows.

**Error handling pattern:** This codebase raises `HTTPException` directly inline (see skeleton.py line 226 `raise HTTPException(status_code=404, detail="report not found")`) rather than a centralized exception handler — follow the same inline-raise style for 429 (rate limit) and 413/422 (upload validation) in the new route, matching RESEARCH.md Patterns 2 and 3.

**Dependency-injection pattern** (session, repeated across skeleton.py):
```python
session: AsyncSession = Depends(get_session)
```
Add the identity dependency the same way: `device_id: str = Depends(get_device_identity)` (RESEARCH.md Code Example §2).

---

### `backend/services/ingestion/rate_limit.py` (service, CRUD guard)

**Analog:** `backend/db/repository.py`'s query style (lines 36-56) — uses `sa.select(...)`, bound parameters, never string-interpolated SQL (per the repository module's own docstring, "no value is ever interpolated into query text (threat T-01-03)"). Follow this exact convention for the rolling-window `COUNT(*)` queries in RESEARCH.md Pattern 2 — use `sa.select(sa.func.count()).select_from(...)`, never raw SQL strings.

**Core pattern:** Copy RESEARCH.md's Pattern 2 code example verbatim as the starting point, but replace the illustrative `sa.cast(Report.location, sa.String)` / raw `ST_DWithin` call with GeoAlchemy2's typed function wrapper, consistent with `backend/models/geo.py`'s `make_point()` helper — i.e. import `from geoalchemy2.functions import ST_DWithin` (or `sa.func.ST_DWithin` bound to the `Geometry` column directly) rather than casting to string. Reuse `make_point()` from `backend/models/geo.py` to build the query-side point, mirroring how `ReportRepository.create()` already does it (repository.py lines 84-90).

**Error handling pattern:** `HTTPException(status_code=429, detail=..., headers={"Retry-After": "..."})` — matches this codebase's inline-raise convention (see `routes/reports.py` section above).

---

### `backend/services/ingestion/upload.py` (service, file-I/O)

**No direct in-repo analog** (first MinIO/Pillow usage in this codebase). Use RESEARCH.md Patterns 3 and 4 verbatim as the reference implementation — they already follow this codebase's conventions (module-level constants like `ALLOWED_FORMATS`/`MAX_UPLOAD_BYTES`, `HTTPException` inline-raise, server-generated keys per D-08).

**Config integration:** Read MinIO client credentials from `backend.core.config.settings` (extend `Settings`, see below) rather than hardcoding, matching how `backend/db/session.py` presumably reads `settings.database_url` (same `Settings` singleton import pattern used throughout: `from backend.core.config import settings`).

---

### `backend/services/ingestion/identity.py` (service, request-response)

**No direct in-repo analog.** Use RESEARCH.md Pattern 1 verbatim. Follow this codebase's module docstring convention (every module in `backend/models/`, `backend/db/` opens with a docstring explaining *why*, referencing the relevant decision ID, e.g. `models/geo.py`'s docstring citing "01-RESEARCH.md Pitfall 1" and threat IDs) — the new `identity.py` should open with a docstring citing D-01/D-02 and Pitfall 4 (secret-default risk).

---

### `backend/models/rate_limit.py` (model, CRUD)

**Analog:** `backend/models/report.py` (lines 1-41) and `backend/models/base.py` (full file).

**Imports + mixin pattern** (report.py lines 10-18; base.py lines 1-18):
```python
import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampedMixin, UUIDPKMixin
```

**Core model pattern:** Use `UUIDPKMixin` (base.py lines 20-32, client-side `uuid.uuid4` default) for the PK — same as every other entity. Use `sa.String(64)`/`sa.String(45)` typed columns with `index=True`, matching `report.py`'s explicit `mapped_column(nullable=..., index=...)` style. RESEARCH.md's `SubmissionAttempt` model (Pattern 2 code block) already follows this exactly — copy it directly, but confirm whether to also inherit `TimestampedMixin` (base.py) instead of hand-rolling `created_at` with `server_default=sa.func.now()` (base.py already provides this identical column — reuse the mixin rather than duplicating it, since `TimestampedMixin.created_at` is byte-for-byte the same definition RESEARCH.md's example hand-writes).

**Docstring convention:** Every model file explains its role relative to the append-only/mutable split (see `report.py` lines 1-8, `repository.py`'s `AppendOnlyRepository` docstrings). RESEARCH.md's own `SubmissionAttempt` docstring already correctly explains why this table is *not* append-only-enforced (operational/ephemeral, prunable) — keep that framing.

---

### `backend/db/repository.py` (extend)

**Analog:** itself — `MutableRepository`/`AppendOnlyRepository` split (lines 59-78), and `ReportRepository` (lines 81-90) as the concrete example of a repository that auto-derives a computed column (`location`) on `create()`.

**Pattern to add:**
```python
class SubmissionAttemptRepository(MutableRepository[SubmissionAttempt]):
    model = SubmissionAttempt
```
A rate-limit counter is mutable in principle (per CONTEXT.md's Reusable Assets note: "a rate-limit counter is mutable (increments), fits `MutableRepository`") — but per RESEARCH.md's design, this phase's chosen shape is append-and-count (one row per attempt, never updated), so `BaseRepository` (create/get/list only) is actually the correct parent, not `MutableRepository`. Confirm final choice against whichever exact schema the plan locks (per-attempt row vs. single incrementing counter row) — both are valid against this codebase's existing split; pick `BaseRepository` if going with RESEARCH.md's `SubmissionAttempt` design (append-and-count, no `update()` needed).

---

### `backend/core/config.py` (extend)

**Analog:** itself (full file, 21 lines).

**Pattern:**
```python
class Settings(BaseSettings):
    database_url: str = "..."
    database_url_sync: str = "..."
    skeleton_routes_enabled: bool = True
    # NEW additions, same flat-field style, no nested config objects:
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "roadtwin"
    minio_secret_key: str = "roadtwin_dev_secret"
    minio_secure: bool = False
    minio_bucket: str = "roadtwin-reports"
    device_id_cookie_secret: str  # NO default — Pitfall 4 requires this to fail loudly if unset
    identity_rate_limit_per_hour: int = 10
    ip_rate_limit_per_hour: int = 20
    gps_cooldown_meters: float = 15.0
    gps_cooldown_seconds: int = 300
    max_upload_bytes: int = 10 * 1024 * 1024
```
Keep the same `model_config = SettingsConfigDict(env_file="backend/.env", ...)` — do not create a second Settings class (D-13 / Reusable Assets explicitly says "extend with MinIO endpoint/credentials here, not a new config module").

---

### `backend/main.py` (extend)

**Analog:** itself (full file, 47 lines) — router-mounting pattern (lines 38-46) and the `logger.warning(...)` pattern for security-relevant startup conditions.

**Pattern:**
```python
if settings.skeleton_routes_enabled:
    from backend.routes import skeleton
    app.include_router(skeleton.router)
    logger.warning(...)

# NEW, unconditional (real endpoint, not diagnostic-gated):
from backend.routes import reports
app.include_router(reports.router)
```
Add MinIO bucket bootstrap (RESEARCH.md Code Example §5) directly below the existing router-mounting block, following the same "module-level side effect guarded by a simple `if`" style already used for the skeleton-routes warning log.

---

### `backend/alembic/versions/0003_ingestion_rate_limit_tables.py` (migration)

**Analog:** `backend/alembic/versions/0002_remaining_entities.py` (full file, 205 lines).

**Header/revision pattern** (lines 1-19):
```python
"""<summary>

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Table creation pattern** (lines 62-86, plain `op.create_table` with `sa.Uuid(as_uuid=True)` PK, no geometry needed for `submission_attempt`):
```python
def upgrade() -> None:
    op.create_table(
        "submission_attempt",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("identity_key", sa.String(64), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_submission_attempt_identity_created", "submission_attempt", ["identity_key", "created_at"])
    op.create_index("ix_submission_attempt_ip_created", "submission_attempt", ["ip_address", "created_at"])


def downgrade() -> None:
    op.drop_table("submission_attempt")
```
Follows 0002's exact "create in dependency order, drop in reverse" convention, and its composite-index pattern (0002 lines 117-121, `ix_road_observation_segment_observed_at`) for the `(identity_key, created_at)` / `(ip_address, created_at)` pairs RESEARCH.md's Pitfall 2 calls for. This migration needs no `op.create_geospatial_table` or new PostGIS enum — it queries the *existing* `Report.location` column directly for the GPS-cooldown check (no new spatial column per Assumption A3), so this migration is plain-table-only, simpler than 0002.

---

### `backend/tests/test_reports_ingestion.py`, `test_ingestion_identity.py`, `test_rate_limit.py` (tests, request-response)

**Analog:** `backend/tests/test_skeleton_e2e.py` (client fixture usage pattern) and `backend/tests/test_report_contract.py` (Pydantic contract-shape assertions) — read via `conftest.py`'s `client` fixture (lines 92-121), which already overrides `get_session` and wraps the app in `httpx.ASGITransport`. New ingestion tests should use the exact same `client` and `session` fixtures — no new fixture-wiring pattern needed for the request-response tests, only additive fixtures for MinIO (see conftest note below).

**Pattern:**
```python
async def test_submit_report_success(client):
    response = await client.post("/reports", files={"image": (...)}, data={"latitude": ..., "longitude": ...})
    assert response.status_code == 201
```
Matches this codebase's async-httpx-client test style throughout `backend/tests/`.

---

### `backend/tests/test_upload.py` (test, file-I/O)

**Analog:** `backend/tests/test_migrations.py`'s "skip if unreachable" pattern, mirrored from `conftest.py`'s `postgres_dsn` fixture (lines 22-35, `pytest.skip("docker-compose postgres service not reachable")`). Add an equivalent `minio_available` fixture in `conftest.py` that attempts `minio_client.bucket_exists(...)` and skips with the same message style if MinIO's docker-compose service isn't running — RESEARCH.md's Validation Architecture section explicitly calls for this (a `minio`-style pytest marker analogous to the existing implicit `postgis` skip-marker).

---

### `frontend/src/pages/ReportSubmitPage.tsx` (component/page)

**Analog:** `frontend/src/pages/SkeletonPage.tsx` — not yet read in full, but `App.tsx`/`main.tsx` establish the page-mounting convention. Since Phase 1 was single-page, this phase's `App.tsx` will need real routing for the first time (per CONTEXT.md D-14/Integration Points) — no existing router analog exists; use standard React Router or a simple state-based page switch consistent with whatever `App.tsx` currently does (read `App.tsx` at plan time to confirm the exact current single-page wiring before introducing routing).

---

### `frontend/src/components/LocationPicker.tsx` (component, event-driven)

**No in-repo analog** (first Leaflet component). Use RESEARCH.md's Code Example §1 verbatim as the reference implementation — it already matches this codebase's TypeScript-first, typed-props functional-component style (see `client.ts`'s explicit `Promise<T>` return types and typed payload imports from `../types`).

---

### `frontend/src/api/client.ts` (extend)

**Analog:** itself (full file, 92 lines) — the `toError()` helper (lines 21-38) and per-endpoint typed async function pattern (e.g. `createReport`, lines 48-60) are the conventions to replicate exactly for `createReportWithImage()` and `getReportImageUrl()`, except the new create function must send `FormData` (multipart) instead of `JSON.stringify`, since the image upload requires `multipart/form-data`:
```typescript
export async function createReportWithImage(
  payload: ReportCreatePayload,
  imageFile: File,
): Promise<Report> {
  const formData = new FormData();
  formData.append("image", imageFile);
  formData.append("latitude", String(payload.latitude));
  formData.append("longitude", String(payload.longitude));
  // ...
  const response = await fetch(REPORTS_URL, { method: "POST", body: formData });
  // NOTE: do not set Content-Type manually for FormData -- the browser sets
  // the multipart boundary automatically; the existing createReport()
  // JSON path sets Content-Type explicitly (line 53) because JSON bodies
  // need it, but FormData bodies must NOT set it manually.
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as Report;
}
```
Reuse `toError()` verbatim (do not duplicate it).

---

## Shared Patterns

### Dependency Injection / Session Access
**Source:** `backend/db/session.py`'s `get_session`, used via `Depends(get_session)` throughout `backend/routes/skeleton.py`.
**Apply to:** `routes/reports.py` and any new service function needing DB access.

### Repository Query Safety (no string-interpolated SQL)
**Source:** `backend/db/repository.py` module docstring + every method body (lines 1-5, 36-56).
**Apply to:** `services/ingestion/rate_limit.py`'s rolling-window count queries — always `sa.select(...)` with bound parameters, never f-string SQL.

### Inline HTTPException Error Handling
**Source:** `backend/routes/skeleton.py` line 226 (`raise HTTPException(status_code=404, detail=...)`).
**Apply to:** All new route/service error paths (429 rate-limit, 413/422 upload validation, 404 not-found) — no centralized exception-handler middleware exists in this codebase; follow the inline-raise convention.

### Coordinate → PostGIS Geometry Construction
**Source:** `backend/models/geo.py`'s `make_point()` / `make_linestring()` — the single, centralized place coordinates become WKT geometry (longitude/latitude ordering deliberately isolated here).
**Apply to:** `services/ingestion/rate_limit.py`'s GPS-cooldown `ST_DWithin` query — always call `make_point()` rather than constructing WKT/geometry inline, per the module's own docstring warning about axis-order bugs.

### Settings Singleton Extension (no new config module)
**Source:** `backend/core/config.py`'s single `Settings`/`settings` pattern.
**Apply to:** All new MinIO/cookie-secret/rate-limit-threshold config — extend the one `Settings` class, import `from backend.core.config import settings` everywhere needed (as `main.py` and `repository.py`'s eventual `rate_limit.py` will).

### UUID PK + Timestamp Mixins
**Source:** `backend/models/base.py`'s `UUIDPKMixin` (client-side `uuid.uuid4` default) and `TimestampedMixin` (`server_default=sa.func.now()`).
**Apply to:** `backend/models/rate_limit.py`'s `SubmissionAttempt` model — inherit both mixins rather than hand-writing an equivalent `id`/`created_at` column.

### Async httpx Test Client Fixture
**Source:** `backend/tests/conftest.py`'s `client` fixture (lines 92-121) — ASGITransport-bound, `get_session` dependency override, per-test rollback via the `session` fixture's outer transaction.
**Apply to:** All four new test files — no new fixture-wiring needed for DB-backed request-response tests; only MinIO reachability needs a new skip-guarded fixture (see `test_upload.py` above).

### Migration Structure (create-in-dependency-order, drop-in-reverse)
**Source:** `backend/alembic/versions/0002_remaining_entities.py`'s `upgrade()`/`downgrade()` pair.
**Apply to:** `0003_ingestion_rate_limit_tables.py`.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/services/ingestion/identity.py` | service | request-response (crypto) | First signed-cookie/identity logic in the codebase; no prior auth/session code exists. Use RESEARCH.md Pattern 1 as the reference, written to match this codebase's docstring/style conventions. |
| `backend/services/ingestion/upload.py` | service | file-I/O | First MinIO/Pillow integration; no prior object-storage code exists. Use RESEARCH.md Patterns 3-4 as the reference. |
| `frontend/src/components/LocationPicker.tsx` | component | event-driven | First Leaflet/map component in the frontend; no prior mapping UI exists. Use RESEARCH.md Code Example §1 as the reference. |

## Metadata

**Analog search scope:** `backend/` (models, schemas, routes, services, db, alembic, tests), `frontend/src/` (pages, api, types)
**Files scanned:** ~30 (all non-`__pycache__` Python files under `backend/`, all files under `frontend/src/`)
**Pattern extraction date:** 2026-09-23
