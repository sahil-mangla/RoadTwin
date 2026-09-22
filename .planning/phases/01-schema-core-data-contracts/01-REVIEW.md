---
phase: 01-schema-core-data-contracts
reviewed: 2026-09-22T00:00:00Z
depth: standard
files_reviewed: 49
files_reviewed_list:
  - backend/alembic.ini
  - backend/alembic/env.py
  - backend/alembic/script.py.mako
  - backend/alembic/versions/0001_initial_report_schema.py
  - backend/alembic/versions/0002_remaining_entities.py
  - backend/core/config.py
  - backend/db/repository.py
  - backend/db/session.py
  - backend/main.py
  - backend/models/__init__.py
  - backend/models/base.py
  - backend/models/detection.py
  - backend/models/enums.py
  - backend/models/geo.py
  - backend/models/maintenance_recommendation.py
  - backend/models/prediction.py
  - backend/models/report.py
  - backend/models/road_health.py
  - backend/models/road_observation.py
  - backend/models/road_segment.py
  - backend/routes/__init__.py
  - backend/routes/skeleton.py
  - backend/schemas/__init__.py
  - backend/schemas/entities.py
  - backend/schemas/report.py
  - backend/schemas/skeleton.py
  - backend/services/__init__.py
  - backend/services/intelligence/__init__.py
  - backend/services/maintenance/__init__.py
  - backend/services/spatial/__init__.py
  - backend/tests/conftest.py
  - backend/tests/test_append_only.py
  - backend/tests/test_migrations.py
  - backend/tests/test_models_roundtrip.py
  - backend/tests/test_report_contract.py
  - backend/tests/test_report_geometry.py
  - backend/tests/test_skeleton_chain.py
  - backend/tests/test_skeleton_e2e.py
  - backend/tests/test_status_lifecycle.py
  - frontend/.gitignore
  - frontend/index.html
  - frontend/package-lock.json
  - frontend/package.json
  - frontend/src/App.tsx
  - frontend/src/api/client.ts
  - frontend/src/main.tsx
  - frontend/src/pages/SkeletonPage.tsx
  - frontend/src/styles.css
  - frontend/src/types.ts
  - frontend/tsconfig.json
  - frontend/tsconfig.node.json
  - frontend/vite.config.ts
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-09-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 49
**Status:** issues_found

## Summary

Reviewed the Phase 1 schema/data-contract deliverable: seven SQLAlchemy models, two Alembic migrations, the repository layer (mutable + append-only), Pydantic contracts, the skeleton diagnostic router, and the React walking-skeleton page, plus the full backend test suite.

The backend half is solid: the append-only/mutable repository split is genuinely enforced (and structurally tested), the shared Postgres enum is wired correctly across `Report`/`Detection`, the lat/lng-to-WKT axis ordering is centralized and independently verified against `ST_X`/`ST_Y`, and the migrations round-trip cleanly with drift detection. No SQL/command injection, no eval-style dangerous calls, no secrets committed.

Two real problems stood out. First, the walking-skeleton form on the frontend disables native HTML validation (`noValidate`) while doing an unchecked `Number(...)` coercion of the latitude/longitude text inputs — an empty field silently becomes `0`, which passes both the browser's (disabled) checks and the backend's `-90..90`/`-180..180` range validation, so a user can submit a dead-empty form and silently get a report persisted at Null Island with zero error feedback. Second, `backend/schemas/entities.py` defines a full set of `*Create`/`*Read` Pydantic contracts for six of the seven entities, documented in its own module docstring as "the ASVS V5 input-validation control point" — but none of it is wired into any route or exercised by any test; it is presently 169 lines of dead code providing zero actual validation.

Also flagged: `ReportCreate.image_path` accepts an arbitrary client-supplied string with no validation, ahead of the Phase 2 upload pipeline that is supposed to be the sole writer of that column; and `MutableRepository.update()` uses bare `setattr` with no check that the field name is an actual mapped column, so a typo silently no-ops instead of raising.

## Critical Issues

### CR-01: Disabled form validation + unchecked numeric coercion lets an empty submission silently persist a report at (0, 0)

**File:** `frontend/src/pages/SkeletonPage.tsx:68-86` (also `:161`)
**Issue:** The form is rendered with `noValidate` (line 161), which disables the browser's enforcement of the `required`/`min`/`max` attributes on the latitude/longitude inputs. `handleSubmit` then does:
```ts
const created = await createReport({
  latitude: Number(latitude),
  longitude: Number(longitude),
  ...
});
```
`Number("")` evaluates to `0`, not `NaN` — so if a user clears the latitude/longitude fields (or a state bug leaves them empty) and submits, the payload silently becomes `{latitude: 0, longitude: 0, ...}`. Both `0` values are inside the backend's `ge=-90,le=90` / `ge=-180,le=180` ranges (`backend/schemas/report.py:12-13`), so the request succeeds and a bogus report is persisted at Null Island with no error shown to the user anywhere in the flow. This defeats both layers of validation (browser and the implicit "did the user type something" check) simultaneously, for the one contract (`Report`'s geometry) this phase is specifically built to get right.
**Fix:** Either remove `noValidate` so the browser enforces `required`, or explicitly guard against empty/invalid input before coercing:
```ts
const parsedLat = latitude.trim() === "" ? NaN : Number(latitude);
const parsedLng = longitude.trim() === "" ? NaN : Number(longitude);
if (Number.isNaN(parsedLat) || Number.isNaN(parsedLng)) {
  setError("Latitude and longitude are required.");
  return;
}
```

## Warnings

### WR-01: `backend/schemas/entities.py` is entirely dead code — the stated "input-validation control point" validates nothing

**File:** `backend/schemas/entities.py:1-169`
**Issue:** The module docstring claims these twelve models (`DetectionCreate`/`Read`, `RoadSegmentCreate`/`Read`, `RoadObservationCreate`/`Read`, `RoadHealthCreate`/`Read`, `PredictionCreate`/`Read`, `MaintenanceRecommendationCreate`/`Read`) are "the ASVS V5 input-validation control point for each entity." A repo-wide search shows none of them is imported by any route (`backend/routes/skeleton.py` only uses `ReportCreate`/`ReportRead` from `backend/schemas/report.py`) or referenced by any test. The entities are created directly via the repository layer with raw kwargs (see `backend/routes/skeleton.py`'s `seed_chain`), bypassing these contracts entirely. As written, this file provides no actual protection and no test coverage — it's aspirational scaffolding that could silently drift from the ORM models (e.g. the missing bbox cross-field check in WR-03 below) without any test ever catching it.
**Fix:** Either wire these schemas into real request/response models on routes that accept this input (even diagnostic ones), or move them out of `schemas/` into a clearly-marked "planned for Phase 2+" location and drop the "control point" claim from the docstring until they're load-bearing.

### WR-02: `ReportCreate.image_path` accepts an unvalidated, client-supplied path ahead of the upload pipeline that is meant to own it

**File:** `backend/schemas/report.py:18`, `backend/models/report.py:39-41`
**Issue:** `backend/models/report.py`'s comment states image upload/population of `image_path` is owned by Phase 2 (INGT-01/INGT-04). Yet `ReportCreate` already exposes `image_path: str | None = None` as directly settable by any caller of `POST /api/skeleton/reports` today, with no length limit (unlike `description`, which has `max_length=2000`) and no format/traversal validation. Nothing currently reads this value back into a filesystem or object-storage call, so it isn't exploitable yet, but the contract as shipped lets a citizen submit any string (e.g. `../../etc/passwd`, or an absolute URL) into a column that Phase 2 is expected to treat as a trusted, server-generated storage key. Once that trust assumption is made, this becomes a path-traversal/SSRF-shaped bug.
**Fix:** Drop `image_path` from `ReportCreate` now (it isn't populated by any current caller) and reintroduce it only once Phase 2 defines it as a server-derived value, or at minimum constrain it (`max_length`, an allow-listed key pattern) so client input can't reach it unfiltered.

### WR-03: `DetectionCreate` bounding-box fields have no cross-field validation

**File:** `backend/schemas/entities.py:19-27`
**Issue:** `bbox_x1`/`bbox_y1`/`bbox_x2`/`bbox_y2` are each independently constrained to `ge=0`, but nothing checks `bbox_x2 > bbox_x1` or `bbox_y2 > bbox_y1`. A client (or, once wired up, the perception layer) can submit a degenerate or inverted bounding box (e.g. `x1=300, x2=100`) and it will pass validation.
**Fix:** Add a `model_validator(mode="after")` that asserts `bbox_x2 > bbox_x1` and `bbox_y2 > bbox_y1`.

### WR-04: `MutableRepository.update()` silently no-ops on an unmapped field name instead of raising

**File:** `backend/db/repository.py:62-66`
**Issue:**
```python
async def update(self, obj: T, **changes) -> T:
    for field, value in changes.items():
        setattr(obj, field, value)
    await self.session.flush()
    return obj
```
`setattr` on a mapped SQLAlchemy instance with a name that isn't a declared column (e.g. a typo like `stauts=...`) just sets a plain Python instance attribute — it is not tracked by the unit-of-work, so `flush()` persists nothing for that "change" and no exception is raised anywhere in the call chain. A caller passing a misspelled kwarg gets a false-positive success.
**Fix:** Validate the field names against the mapper before assigning, e.g.:
```python
mapper = sa.inspect(type(obj))
for field, value in changes.items():
    if field not in mapper.attrs:
        raise ValueError(f"{type(obj).__name__} has no mapped attribute '{field}'")
    setattr(obj, field, value)
```

## Info

### IN-01: `PredictionCreate.confidence` has no bounds, unlike its sibling `failure_probability`

**File:** `backend/schemas/entities.py:128-135`
**Issue:** `failure_probability` is constrained `ge=0, le=1`, but `confidence: float | None = None` (line 134) has no bounds at all, despite representing the same kind of [0,1] probability quantity per the rest of the codebase's convention (e.g. `Detection.confidence`, `RoadObservation.confidence` are both `ge=0, le=1`).
**Fix:** Add `Field(default=None, ge=0, le=1)` to match the convention used everywhere else in this file.

### IN-02: Hardcoded default database credentials in `core/config.py`

**File:** `backend/core/config.py:12-13`
**Issue:** `database_url`/`database_url_sync` default to `postgresql+asyncpg://roadtwin:roadtwin_dev@localhost:5432/roadtwin` when no `.env`/env var is present. This is clearly dev-only (`roadtwin_dev`) and documented as such, but it means running the app with no configuration at all silently succeeds against a guessable local dev credential rather than failing loudly if `backend/.env` is missing.
**Fix:** Low priority given the `_dev` suffix signals intent, but consider making `database_url`/`database_url_sync` required (no default) so a misconfigured non-dev environment fails fast instead of silently defaulting.

### IN-03: Skeleton form doesn't reset after a successful submission

**File:** `frontend/src/pages/SkeletonPage.tsx:68-86`
**Issue:** `handleSubmit` adds the created report to `reports` state but never resets `latitude`/`longitude`/`accuracy`/`description`, so a user who clicks Submit twice in a row (without editing anything) creates two near-identical reports with no indication that's what happened.
**Fix:** Reset the form fields to their defaults (or clear them) on successful submission.

---

_Reviewed: 2026-09-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
