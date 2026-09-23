# Phase 2: Ingestion, Citizen Identity & Rate Limiting - Research

**Researched:** 2026-09-23
**Domain:** Citizen-facing crowdsourced submission ingestion — multipart image upload, object storage, lightweight non-account identity, application-layer anti-spam rate limiting
**Confidence:** MEDIUM-HIGH (core FastAPI/Postgres/MinIO patterns are well-established and version-verified against live registries; the Postgres-backed rate limiter is a hand-rolled pattern with no single canonical library, so it carries MEDIUM confidence and is designed explicitly, not borrowed off-the-shelf)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Citizen Identity (INGT-02)**
- **D-01:** Lightweight identity = a server-issued device/session identifier persisted as an HttpOnly cookie, generated on first visit if absent. This alone satisfies INGT-02's "device/session ID **or** email" wording.
- **D-02:** No email-capture field is built in this phase.

**Rate Limiting & Anti-Spam (INGT-03)**
- **D-03:** Rate-limit state lives in **Postgres** (a simple counter/window table), not Redis.
- **D-04:** Rate limiting keys on **both** the device-identity cookie (D-01) **and** the client IP — whichever is closer to its limit governs.
- **D-05:** In addition to identity-rate limiting, add a **minimum time-between-reports for the same GPS point** (a StreetBump-style submission cooldown).
- **D-06:** Exceeding either limit returns **HTTP 429 with a clear retry-after value** — never a silent drop.
- Exact numeric thresholds (requests/hour, cooldown radius/duration) are Claude's Discretion.

**Image Upload Path (INGT-04)**
- **D-07:** Upload flows **through the FastAPI server** (multipart `UploadFile`), not a direct-to-MinIO presigned PUT from the browser.
- **D-08:** After receiving and validating the upload (format/size), the server writes it to MinIO and persists the object key on `Report` — gaining real constraints: max length, allow-listed key pattern, no client-supplied paths.
- **D-09:** Retrieval uses **short-lived presigned GET URLs**, never permanent public URLs.
- Content-based validation ("does this photo actually show a road") is explicitly **not** this phase's job — deferred to YOLO's own no-detection case in Phase 3. Phase 2 validates format/size only.

**GPS Capture UX (INGT-01)**
- **D-10:** Attempt the browser Geolocation API automatically on page load. Whether it succeeds or fails, the result is always shown on a Leaflet map for the citizen to **confirm or drag-adjust before submitting**. On failure/denial, the map starts at a default view and the citizen places the pin manually. One unified confirmation UI covers both paths.
- **D-11:** A submission with poor GPS accuracy is **accepted and flagged, never hard-rejected** at ingestion. A non-blocking "location may be imprecise" UI hint above some accuracy threshold is Claude's Discretion to size.

**Code Organization**
- **D-12:** New citizen-facing route file: `backend/routes/reports.py`. `backend/routes/skeleton.py` stays untouched (internal diagnostic tooling).
- **D-13:** New `backend/services/ingestion/` package for identity/rate-limit/upload logic — parallel to `spatial/`, `intelligence/`, `maintenance/`.
- **D-14:** New frontend page for the real citizen report form (not `SkeletonPage.tsx`). Reuse the established `api/client.ts` fetch-client pattern and Phase 1's CR-01 validate-before-submit lesson.

### Claude's Discretion
- Exact rate-limit numbers (requests per identity per hour; GPS-point cooldown radius and duration).
- Exact cookie name, expiry, and signing approach for the device-identity token.
- Exact Postgres rate-limit table schema (single shared counter table vs. one per limiter).
- Exact image size/format allow-list (e.g., JPEG/PNG/HEIC, max MB).
- Exact "imprecise location" accuracy threshold (D-11) for the non-blocking UI hint.
- Leaflet default map center/zoom when GPS is unavailable and the citizen must place a pin from scratch.

### Deferred Ideas (OUT OF SCOPE)
None — `--auto` mode, no live user turn. The one boundary worth restating: async YOLO inference triggering and arq/Redis worker setup belong to Phase 3, not this phase. Do not pull that infrastructure forward.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGT-01 | Citizen can submit a report with image + GPS (auto-captured or manual pin) + timestamp + optional description | GPS Capture UX section (react-leaflet draggable marker + Geolocation API pattern), Code Examples §1, §4 |
| INGT-02 | Citizen submissions are attributed to a lightweight identity (device/session ID or email — full account system not required) | Standard Stack (itsdangerous), Architecture Pattern "Signed Cookie Device Identity", Code Examples §2 |
| INGT-03 | Submission endpoint enforces rate limiting per identity/IP to prevent spam and evidence-score gaming | Architecture Pattern "Postgres Dual-Key Rate Limiter", Common Pitfalls §1-3, Code Examples §3 |
| INGT-04 | Uploaded images are stored in object storage addressable by the Report record | Standard Stack (minio), Architecture Pattern "Through-Server Upload to MinIO", Code Examples §5-6 |
</phase_requirements>

## Summary

Phase 2 wires the first real citizen-facing write path in RoadTwin: a synchronous, non-ML `POST /reports` request that must (a) validate and durably persist a multipart image + GPS + optional description, (b) attribute the submission to a frictionless, cookie-based device identity, (c) reject spam via a dual-key (identity + IP) Postgres rate limiter plus a same-location submission cooldown, and (d) write the image to MinIO with only a presigned-GET-retrievable reference stored on `Report`. None of this touches YOLO, arq, or Redis — those are Phase 3's concern and must not be pulled forward.

Every piece of this phase composes existing, boring, well-documented primitives rather than needing new infrastructure: FastAPI's own `UploadFile` + `python-multipart` (already a transitive dependency of FastAPI's `[standard]` extras) for the multipart boundary, Pillow for format/decompression-bomb validation and EXIF-orientation normalization, `exifread` for optional EXIF-GPS fallback extraction, `itsdangerous` for a signed (not merely opaque) HttpOnly cookie, the official `minio` Python SDK for both the through-server `put_object` write and the `presigned_get_object` read, and a hand-rolled Postgres counter table (no existing Postgres-native rate-limiting library is fit for purpose at this scale — see Don't Hand-Roll below for the one caveat). The one genuinely novel piece of design in this phase is the dual-key rate limiter and cooldown table shape, because CONTEXT.md's D-03/D-04/D-05 constraints (Postgres, not Redis; two independent keys; a third spatial-cooldown rule) don't map onto any single off-the-shelf package — this is designed explicitly below with a concrete schema and query pattern.

**Primary recommendation:** Build `backend/services/ingestion/` as three focused modules — `identity.py` (signed cookie mint/verify), `rate_limit.py` (Postgres counter reads/writes for both the identity+IP dual-key check and the GPS-cooldown check), and `upload.py` (Pillow validation + MinIO put + presigned-GET helper) — and keep `routes/reports.py` a thin orchestration layer that calls all three in sequence before invoking `ReportRepository.create()`. Do not introduce any queue, worker process, or Redis client in this phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| GPS auto-capture + map confirm/drag UI | Browser / Client | — | Browser Geolocation API and Leaflet marker drag state are inherently client-side; the server never re-derives GPS, it only validates ranges already enforced by `ReportCreate`. |
| Device/session identity issuance & verification | API / Backend | Browser / Client (cookie storage only) | The signing secret and verification logic must live server-side (ASVS V6); the browser is a passive bearer of the opaque signed cookie value, never able to construct or alter it. |
| Rate-limit counter state (identity+IP, GPS-cooldown) | Database / Storage | API / Backend (read/write logic) | Counters must survive process restarts and be shared across multiple Uvicorn workers — this is exactly what D-03 already resolved in favor of Postgres over in-memory. |
| Multipart image upload validation (format/size) | API / Backend | — | Must happen before any bytes are persisted; a compromised or malformed image cannot be allowed to reach MinIO or the DB row. |
| Image binary storage | Database / Storage (MinIO) | — | CLAUDE.md's "What NOT to Use" explicitly forbids storing image bytes as Postgres bytea; MinIO is the addressed object store, Postgres only holds the reference key. |
| Report record persistence (metadata + image key) | Database / Storage | API / Backend (repository layer) | `Report` row via existing `ReportRepository`/`MutableRepository` pattern from Phase 1 — no new entity. |
| Presigned URL generation for image retrieval | API / Backend | Database / Storage (MinIO) | Presigned URLs must be minted per-request server-side (short expiry, no permanent public URL) — never generated or cached client-side. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| python-multipart | 0.0.32 [VERIFIED: pip index versions, 2026-09-23] | Parses the `multipart/form-data` request body FastAPI needs for any `UploadFile` parameter | Already listed as a required companion in CLAUDE.md's stack doc; without it, any endpoint declaring `UploadFile` raises a runtime error at first request. Confirmed current on PyPI. |
| Pillow | 12.3.0 [VERIFIED: pip index versions, 2026-09-23] | Image decode, format validation, decompression-bomb guard, EXIF-orientation normalization before storage | CLAUDE.md names it explicitly; it is also `ultralytics`' own image-I/O dependency (Phase 3), so no new transitive dependency is introduced. |
| minio | 7.2.20 [VERIFIED: pip index versions, 2026-09-23] | Official S3-compatible Python SDK — `put_object` (through-server write) and `presigned_get_object` (short-lived retrieval) | CLAUDE.md locks MinIO as the object store; this is the vendor's own official client, not a third-party wrapper. |
| itsdangerous | 2.2.0 [VERIFIED: pip index versions, 2026-09-23] | Cryptographically signs the device-identity cookie payload so it cannot be forged or replayed with a different device ID | Not explicitly named in CLAUDE.md, but is the de facto standard signing library in the FastAPI/Starlette ecosystem (Starlette's own `SessionMiddleware` uses it internally) — using it directly here keeps the identity cookie independent of a full session-middleware framework, matching D-01's "lightweight, not a full account system" intent. [ASSUMED — package choice, not in CLAUDE.md's explicit list; confirm during planning discretion.] |
| leaflet | 1.9.4 [VERIFIED: npm view, 2026-09-23] | Core mapping library for GPS confirm/drag UI | Locked by CLAUDE.md; do not adopt Leaflet 2.0 (alpha). |
| react-leaflet | 5.0.0 [VERIFIED: npm view, 2026-09-23] | React bindings for Leaflet | Locked by CLAUDE.md; requires React 19 as peer dependency — confirmed via `npm view react-leaflet peerDependencies` → `{leaflet: '^1.9.0', react: '^19.0.0', 'react-dom': '^19.0.0'}`, matching the already-pinned React 19.3.0. |
| @types/leaflet | 1.9.22 [VERIFIED: npm view, 2026-09-23] | TypeScript types for Leaflet | Needed since the project is TypeScript-first (Phase 1 established this convention). |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| exifread | 3.5.1 [VERIFIED: pip index versions, 2026-09-23] | Fallback EXIF-GPS extraction when the browser Geolocation API is denied/unavailable and the citizen didn't drop a manual pin either, but the photo itself carries embedded GPS EXIF tags | CLAUDE.md names it as a paired option to Pillow for "EXIF GPS extraction on upload." Use only as a fallback signal (e.g., to pre-fill the map pin for the citizen to confirm/drag, per D-10's "always shown for confirmation" rule) — never as a silent, unconfirmed coordinate source, since D-10 requires visual confirmation of every coordinate regardless of source. |
| pydantic-settings | already installed (2.x, per `backend/core/config.py`) | Extend `Settings` with MinIO endpoint/bucket/access-key/secret-key and cookie-signing-secret config | No new library — reuse the existing `Settings` class per D-13's code-organization note ("extend, not a new config module"). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled Postgres counter table | `slowapi` (Redis-backed) | Rejected outright by D-03 — introduces Redis a phase early, against the explicit sequencing decision. |
| Hand-rolled Postgres counter table | `fastapi-limiter` (Redis-backed) | Same rejection as above — every mainstream FastAPI rate-limiting package assumes Redis or an in-memory store; none is Postgres-native, which is why this phase hand-rolls a small counter table (see Don't Hand-Roll). |
| `itsdangerous`-signed cookie | Starlette's built-in `SessionMiddleware` | `SessionMiddleware` is itself `itsdangerous`-backed but stores an entire session dict client-side and is framework-wide (affects every route); a purpose-built single-value signed cookie for device identity is a smaller, more auditable surface for exactly one job. |
| `exifread` for GPS fallback | Pillow's own `Image.getexif()` / `ExifTags` | Pillow *can* read EXIF GPS IFD tags directly (avoiding one extra dependency), but its GPS tag API is lower-level (raw IFD dict, manual DMS→decimal conversion) versus `exifread`'s friendlier tag access; CLAUDE.md names both, so either is acceptable — `exifread` is recommended for readability, Pillow's built-in path is a valid discretion-based alternative if minimizing dependencies is prioritized. |
| Direct-to-MinIO presigned PUT | Through-server multipart upload (D-07, locked) | Rejected by CONTEXT.md — a presigned PUT bypasses the server entirely, making server-side EXIF extraction and format/size validation impossible before the object lands in MinIO. |

**Installation:**
```bash
# backend/requirements.txt additions
echo "minio>=7.2.20,<7.3" >> backend/requirements.txt
echo "Pillow>=12.3.0,<13.0" >> backend/requirements.txt
echo "itsdangerous>=2.2.0,<3.0" >> backend/requirements.txt
echo "exifread>=3.5.1,<4.0" >> backend/requirements.txt
# python-multipart is already a transitive dependency of fastapi[standard]/uvicorn[standard]
# but pin it explicitly since backend/requirements.txt does not use the [standard] extra:
echo "python-multipart>=0.0.32,<0.1" >> backend/requirements.txt

# frontend/package.json additions
cd frontend && npm install leaflet@1.9.4 react-leaflet@5.0.0
npm install --save-dev @types/leaflet@1.9.22
```

**Version verification:** All six package/version pairs above were checked directly against PyPI (`pip index versions`) and the npm registry (`npm view`) on 2026-09-23 — see inline `[VERIFIED: ...]` tags. None relies on CLAUDE.md's training-data-era version numbers uncrossed with a live registry check.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| leaflet | npm | 13+ yrs (current release 2023) | 5.3M/wk | github.com/Leaflet/Leaflet | OK | Approved |
| react-leaflet | npm | 10+ yrs (current release 2024) | 2.6M/wk | github.com/PaulLeCam/react-leaflet | OK | Approved |
| @types/leaflet | npm | long-lived (DefinitelyTyped) | 4.4M/wk | github.com/DefinitelyTyped/DefinitelyTyped | OK | Approved |
| minio | PyPI | official vendor SDK, actively released | download-count API unavailable to checker | github.com/minio/minio-py | SUS (`unknown-downloads` only) | Approved — see note below |
| Pillow | PyPI | 10+ yrs, PIL-fork successor, ubiquitous | download-count API unavailable to checker | github.com/python-pillow/Pillow | SUS (`unknown-downloads` only) | Approved — see note below |
| python-multipart | PyPI | FastAPI's own recommended multipart dependency | download-count API unavailable to checker | github.com/Kludex/python-multipart | SUS (`unknown-downloads` only) | Approved — see note below |
| itsdangerous | PyPI | Pallets-project (Flask ecosystem) signing library, 10+ yrs | download-count API unavailable to checker | github.com/pallets/itsdangerous | SUS (`unknown-downloads` only) | Approved — see note below |
| exifread | PyPI | actively released fork of exif-py, long-lived project | download-count API unavailable to checker | (checker returned no repo URL; actual project is github.com/ianare/exif-py per web search) | SUS (`unknown-downloads` + `no-repository`) | Approved with checkpoint — see note below |

**Note on the PyPI `SUS` verdicts:** The package-legitimacy checker's `unknown-downloads` signal reflects a tooling limitation — no PyPI download-count API is wired into the checker, so every PyPI package defaults to this flag regardless of actual popularity. This is **not** evidence of slopsquatting. All four PyPI packages (`minio`, `Pillow`, `python-multipart`, `itsdangerous`) are long-established, officially maintained projects with real GitHub repos, confirmed via `pip index versions` against the live registry and cross-referenced against CLAUDE.md's pre-existing stack doc (which independently named all of them by version with its own PyPI-JSON-API verification). `exifread`'s additional `no-repository` flag is because PyPI's project metadata for this package does not populate `project_urls` consistently — the actual source is `github.com/ianare/exif-py`, confirmed via web search, and the package is also named explicitly in CLAUDE.md.

**Packages removed due to `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `minio`, `Pillow`, `python-multipart`, `itsdangerous` (tooling-limitation false positive, no checkpoint needed beyond normal install verification), `exifread` (same tooling limitation, plus a metadata gap — planner should add one lightweight `checkpoint:human-verify` before this specific install, confirming `pip show exifread` resolves to `github.com/ianare/exif-py` and not an impostor package, since this is the one dependency where the checker could not independently confirm a repo URL).

## Architecture Patterns

### System Architecture Diagram

```
Citizen's browser
   │
   │ 1. Page load: attempt navigator.geolocation.getCurrentPosition()
   │    (succeeds → lat/lon/accuracy; fails/denied → no auto-fill)
   ▼
Leaflet map (draggable marker)
   │ 2. Citizen confirms auto-captured pin OR drags/places pin manually
   │    (D-10: one unified confirm-before-submit UI, no silent auto-submit)
   ▼
Citizen fills description (optional) + attaches image file
   │ 3. Client-side validate-before-submit (Phase 1 CR-01 pattern):
   │    reject empty/out-of-range lat-lon before firing the request
   ▼
POST /reports  (multipart/form-data: image file + JSON fields)
   │
   ▼
┌─────────────────────────── FastAPI: routes/reports.py ───────────────────────────┐
│                                                                                    │
│  4. Identity middleware/dependency:                                              │
│     - Read device-id cookie; if absent or signature invalid, mint a new one       │
│       (services/ingestion/identity.py — itsdangerous-signed, HttpOnly, Secure)    │
│                                                                                    │
│  5. Rate-limit check (services/ingestion/rate_limit.py):                         │
│     - Query Postgres counter table: has this identity OR this IP exceeded        │
│       its rolling-window quota? → 429 + Retry-After if yes                       │
│     - Query GPS-cooldown table: has ANY report landed within                     │
│       [radius] of (lat, lon) in the last [cooldown_seconds]? → 429 if yes         │
│                                                                                    │
│  6. Upload validation (services/ingestion/upload.py):                           │
│     - Enforce max content-length before reading full body into memory            │
│     - Pillow: Image.open() + verify() + decompression-bomb guard +               │
│       format allow-list (JPEG/PNG/HEIC) + exif_transpose() normalization         │
│     - Reject (422) on failure — never silently accept a corrupt/oversized file   │
│                                                                                    │
│  7. Optional EXIF-GPS fallback (exifread) if no GPS was supplied at all —        │
│     result still routed back through the map-confirm UI, never auto-submitted    │
│                                                                                    │
│  8. MinIO write: minio_client.put_object(bucket, object_key, ...)                │
│     - object_key generated server-side (UUID-based), never client-supplied       │
│                                                                                    │
│  9. ReportRepository.create(...) — persists Report row with image_path =         │
│     the MinIO object key, plus lat/lon/accuracy/timestamp/description            │
│                                                                                    │
│ 10. Record this submission in the rate-limit counter + GPS-cooldown tables       │
│     (same transaction as the Report insert, so a failed insert doesn't           │
│     still consume a rate-limit slot)                                             │
│                                                                                    │
│ 11. Return 201 with ReportRead (no image bytes, no enqueue call — Phase 3        │
│     picks up async inference triggering later, NOT built here)                   │
└────────────────────────────────────────────────────────────────────────────────┘
   │
   ▼
Citizen sees confirmation ("report received") — no processing/YOLO status shown yet,
that surfaces only once Phase 3's async pipeline exists.

┌────────────── Later: GET /reports/{id}/image-url (retrieval path) ──────────────┐
│ FastAPI generates minio_client.presigned_get_object(bucket, object_key,          │
│ expires=short_timedelta) on demand — never a stored/cached permanent URL         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure
```
backend/
├── routes/
│   ├── skeleton.py              # unchanged — Phase 1 diagnostic tooling
│   └── reports.py                # NEW (D-12) — POST /reports, GET /reports/{id}/image-url
├── services/
│   ├── ingestion/                 # NEW (D-13)
│   │   ├── __init__.py
│   │   ├── identity.py            # mint/verify signed device-id cookie
│   │   ├── rate_limit.py          # dual-key counter + GPS-cooldown checks
│   │   └── upload.py              # Pillow validation + MinIO put/presign helpers
│   ├── spatial/                   # unchanged stub (Phase 4)
│   ├── intelligence/               # unchanged stub (Phase 5/6)
│   └── maintenance/                # unchanged stub (Phase 7)
├── models/
│   └── rate_limit.py               # NEW — SubmissionCounter / GpsCooldown SQLAlchemy models
├── db/
│   └── repository.py                # extend with RateLimitRepository (D-13 parallel pattern)
├── core/
│   └── config.py                    # extend Settings: minio_endpoint, minio_bucket,
│                                     #   minio_access_key, minio_secret_key, minio_secure,
│                                     #   device_id_cookie_secret, rate limit thresholds
└── alembic/versions/
    └── 0003_ingestion_rate_limit_tables.py   # NEW migration

frontend/src/
├── pages/
│   ├── SkeletonPage.tsx            # unchanged
│   └── ReportSubmitPage.tsx        # NEW (D-14) — real citizen report form + map
├── components/
│   └── LocationPicker.tsx           # NEW — Leaflet map + draggable marker + geolocation hook
├── api/
│   └── client.ts                    # extend with createReportWithImage(), getReportImageUrl()
└── types.ts                         # extend ReportCreatePayload for multipart shape
```

### Pattern 1: Signed Cookie Device Identity (no full auth)

**What:** On first request without a valid device-id cookie, mint a UUID, sign it with `itsdangerous.URLSafeTimedSerializer`, and set it as an `HttpOnly`, `Secure`, `SameSite=Lax` cookie with a long expiry (e.g., 1 year). On every request, verify the signature before trusting the embedded UUID; treat verification failure identically to "no cookie" (mint a fresh one) rather than rejecting the request.
**When to use:** Every `POST /reports` (and future `EVID-04` upvote) request — this is the identity anchor D-01/D-02 require, deliberately without a password or email.
**Example:**
```python
# backend/services/ingestion/identity.py
# Source: itsdangerous docs (URLSafeTimedSerializer) + Starlette SessionMiddleware
# pattern (same underlying library, purpose-built single-value cookie here)
import uuid
from itsdangerous import URLSafeTimedSerializer, BadSignature

from backend.core.config import settings

_serializer = URLSafeTimedSerializer(settings.device_id_cookie_secret, salt="roadtwin-device-id")

COOKIE_NAME = "rt_device_id"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


def read_or_mint_device_id(raw_cookie: str | None) -> tuple[str, str | None]:
    """Returns (device_id, new_signed_cookie_value_or_None).

    new_signed_cookie_value is non-None only when a fresh cookie must be set
    on the response (missing or invalid incoming cookie).
    """
    if raw_cookie:
        try:
            device_id = _serializer.loads(raw_cookie, max_age=COOKIE_MAX_AGE)
            return device_id, None
        except BadSignature:
            pass  # fall through to mint fresh
    device_id = str(uuid.uuid4())
    return device_id, _serializer.dumps(device_id)
```

### Pattern 2: Postgres Dual-Key Rate Limiter + GPS Cooldown

**What:** A small, append-and-count Postgres table records every submission attempt with its `identity_key` (device-id UUID) and `ip_address`. The rate-limit check counts rows for *either* key within a rolling window (e.g., last 60 minutes) and rejects if either count is at/above its threshold — "whichever is closer to its limit governs" per D-04 means checking both and rejecting on the first breach. A second, separate query checks for any prior submission within a given radius/time of the new submission's (lat, lon) for the GPS-cooldown rule (D-05), using the existing PostGIS `location` column on `Report` directly (via `ST_DWithin`) rather than a second geometry column, since `Report` rows already carry a spatial index.
**When to use:** As a dependency/guard invoked at the top of `POST /reports`, before any image bytes are read or MinIO is touched — cheap Postgres reads should fail fast, before expensive I/O.
**Trade-offs:** A rolling-window count-query (vs. a fixed-window counter increment) is slightly more expensive per request (a `SELECT COUNT(*) ... WHERE created_at > now() - interval`) but avoids the classic fixed-window boundary-burst problem search results warned about, and at RoadTwin's v1 traffic level (well under 10 req/s per CLAUDE.md) this cost is negligible. A lightweight periodic cleanup job (or just an index + a `WHERE created_at > now() - interval '7 days'` filter on every query) keeps the table from growing unbounded — plan for this even if the cleanup job itself lands in a later phase.

**Example:**
```python
# backend/models/rate_limit.py — NEW model
import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPKMixin


class SubmissionAttempt(UUIDPKMixin, Base):
    """One row per report-submission attempt (accepted or rejected).

    Deliberately NOT append-only-repository-enforced like RoadObservation/
    RoadHealth/Prediction (SCHM-02) -- this table is operational/ephemeral
    rate-limit telemetry, not longitudinal intelligence-layer evidence, so
    periodic pruning of old rows is expected and safe.
    """

    __tablename__ = "submission_attempt"

    identity_key: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(sa.String(45), nullable=False, index=True)  # IPv6-safe length
    created_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True
    )
```

```python
# backend/services/ingestion/rate_limit.py
# Source: pattern synthesized from search results on Postgres-backed
# (non-Redis) rate limiting -- rolling-window COUNT query, not fixed-window
# counter increment, to avoid boundary-burst false negatives.
import datetime as dt

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.rate_limit import SubmissionAttempt
from backend.models.report import Report

IDENTITY_LIMIT_PER_HOUR = 10  # Claude's Discretion default -- size against
IP_LIMIT_PER_HOUR = 20        # a plausible citizen-reporting cadence, tune in planning.
GPS_COOLDOWN_METERS = 15
GPS_COOLDOWN_SECONDS = 300


async def enforce_rate_limits(
    session: AsyncSession, identity_key: str, ip_address: str, lat: float, lon: float
) -> None:
    window_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)

    identity_count = await session.scalar(
        sa.select(sa.func.count()).select_from(SubmissionAttempt).where(
            SubmissionAttempt.identity_key == identity_key,
            SubmissionAttempt.created_at >= window_start,
        )
    )
    ip_count = await session.scalar(
        sa.select(sa.func.count()).select_from(SubmissionAttempt).where(
            SubmissionAttempt.ip_address == ip_address,
            SubmissionAttempt.created_at >= window_start,
        )
    )
    if identity_count >= IDENTITY_LIMIT_PER_HOUR or ip_count >= IP_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="Submission rate limit exceeded. Please try again later.",
            headers={"Retry-After": "3600"},
        )

    cooldown_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=GPS_COOLDOWN_SECONDS)
    nearby_recent = await session.scalar(
        sa.select(sa.func.count()).select_from(Report).where(
            Report.created_at >= cooldown_start,
            sa.func.ST_DWithin(
                sa.cast(Report.location, sa.String),  # illustrative -- use geoalchemy2 functions directly
                sa.func.ST_MakePoint(lon, lat),
                GPS_COOLDOWN_METERS,
            ),
        )
    )
    if nearby_recent:
        raise HTTPException(
            status_code=429,
            detail="A report near this location was just submitted. Please wait before submitting another.",
            headers={"Retry-After": str(GPS_COOLDOWN_SECONDS)},
        )
```

*(Note: the `ST_DWithin` call above is illustrative — the planner should use `geoalchemy2`'s typed spatial function wrappers, consistent with `backend/models/geo.py`'s existing `make_point` helper, rather than raw string casts. Confirm the exact GeoAlchemy2 idiom during planning by reading `backend/models/geo.py` and `backend/db/repository.py`'s existing spatial-column usage.)*

### Pattern 3: Through-Server Upload with Format/Size Validation Before MinIO Write

**What:** Read the `UploadFile`'s content-length header first (reject oversized requests before consuming the stream); then use Pillow to `Image.open()` + `.verify()` the bytes, checking format against an allow-list and enforcing `Image.MAX_IMAGE_PIXELS` as a hard error (not just a warning) to guard against decompression bombs; then call `ImageOps.exif_transpose()` to normalize orientation before writing to MinIO — this prevents sideways/upside-down photos in the citizen-facing map/dashboard later.
**When to use:** Inside `services/ingestion/upload.py`, invoked by `routes/reports.py` after the rate-limit checks pass and before the MinIO `put_object` call.
**Example:**
```python
# backend/services/ingestion/upload.py
# Source: Pillow security docs (MAX_IMAGE_PIXELS, DecompressionBombError,
# format allow-listing) + ImageOps.exif_transpose pattern from web search.
import io
import uuid

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

ALLOWED_FORMATS = {"JPEG", "PNG", "HEIF"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB -- Claude's Discretion default


async def validate_and_normalize_image(upload: UploadFile) -> bytes:
    raw = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds maximum upload size.")

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()  # cheap structural check; re-open below to actually process
        img = Image.open(io.BytesIO(raw))
        if img.format not in ALLOWED_FORMATS:
            raise HTTPException(status_code=422, detail=f"Unsupported image format: {img.format}")
    except Image.DecompressionBombError:
        raise HTTPException(status_code=422, detail="Image rejected: exceeds safe pixel-count limit.")
    except Exception:
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid image.")

    img = ImageOps.exif_transpose(img)  # normalize rotation before storage
    buf = io.BytesIO()
    img.save(buf, format=img.format)
    return buf.getvalue()


def generate_object_key(report_id: uuid.UUID, extension: str) -> str:
    # Server-generated only -- D-08 explicitly forbids client-supplied paths.
    return f"reports/{report_id}.{extension}"
```

### Pattern 4: MinIO Put + Presigned GET

**What:** Write with `client.put_object(bucket, object_key, io.BytesIO(data), length=len(data), content_type=...)`; read access is always minted on-demand via `client.presigned_get_object(bucket, object_key, expires=timedelta(minutes=15))` — never stored or returned as a permanent link.
**When to use:** `put_object` at submission time in `routes/reports.py`; `presigned_get_object` at read time from a dedicated `GET /reports/{id}/image-url` endpoint (or embedded in `ReportRead` responses computed fresh per request).
**Example:**
```python
# backend/services/ingestion/upload.py (continued)
# Source: minio-py official examples (presigned_get_object.py, put_object usage)
import datetime as dt
from minio import Minio

from backend.core.config import settings

minio_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)

BUCKET = "roadtwin-reports"


def put_report_image(object_key: str, data: bytes, content_type: str) -> None:
    minio_client.put_object(
        BUCKET, object_key, io.BytesIO(data), length=len(data), content_type=content_type
    )


def get_presigned_image_url(object_key: str) -> str:
    return minio_client.presigned_get_object(
        BUCKET, object_key, expires=dt.timedelta(minutes=15)
    )
```

### Anti-Patterns to Avoid
- **Reading the entire upload into memory without a size check first:** always cap `upload.read(MAX_BYTES + 1)` and reject if the result exceeds the cap, rather than reading unboundedly and checking `len()` after — an attacker can otherwise exhaust server memory with one request.
- **Rejecting a submission outright for low GPS accuracy:** D-11 locks "accept and flag, never hard-reject" — a validation function that raises on high `gps_accuracy_meters` violates this decision.
- **Treating a rate-limit rejection as a silent 200 with a hidden flag:** D-06 requires a real 429 with `Retry-After` — a "soft" rate limit that still returns 201 defeats the purpose and hides the problem from the citizen and from monitoring.
- **Storing the MinIO object key as a client-supplied string:** D-08 requires the server to generate the key (e.g., from the Report's own UUID) — never accept a `filename`/`path` field from the request body and use it directly as the MinIO key (path-traversal / object-overwrite risk).
- **Pulling arq/Redis into this phase "since we'll need it soon anyway":** explicitly out of scope per CONTEXT.md's domain boundary — do not add a queue, worker, or Redis dependency in Phase 2's plans.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Cookie signing/tamper-detection | A custom HMAC scheme on raw cookie bytes | `itsdangerous.URLSafeTimedSerializer` | Handles timing-safe comparison, timestamp-based expiry, and URL-safe base64 encoding correctly — a hand-rolled HMAC comparison is a classic timing-attack surface. |
| Image format sniffing / decompression-bomb protection | Manual magic-byte checks or a hand-written pixel-count cap | Pillow's `Image.open()` + `MAX_IMAGE_PIXELS` + `DecompressionBombError` | Pillow's format detection and bomb-guard are already correct and battle-tested; a hand-rolled magic-byte sniffer will miss edge cases (e.g., valid-but-malicious multi-frame TIFFs) that Pillow's own security hardening already accounts for. |
| S3-compatible object storage client (auth signing, multipart uploads, presigned URL generation) | A raw `httpx` client hitting MinIO's REST API directly | The official `minio` Python SDK | AWS SigV4 request signing and presigned-URL construction are non-trivial to get right (clock skew, canonical request formatting) — the SDK is free and exists exactly for this. |
| EXIF orientation/GPS parsing | Manual TIFF/EXIF byte-offset parsing | Pillow's `ImageOps.exif_transpose()` / `exifread` | EXIF's endianness and IFD-offset structure is a well-known source of subtle bugs; both libraries already handle the format's edge cases (e.g., missing GPSInfo IFD, DMS-to-decimal conversion). |

**Key insight:** Every "don't hand-roll" item above is a security- or correctness-critical parsing/crypto operation with a mature, narrowly-scoped library already in CLAUDE.md's locked stack — the only genuinely new *design* surface in this phase is the rate-limit table shape and query pattern (Pattern 2 above), precisely because no existing library targets "Postgres-only, dual-key, plus a spatial cooldown" as a packaged solution. Keep that one piece of hand-rolled logic small, well-tested, and isolated in `rate_limit.py` — do not let it sprawl into a general-purpose rate-limiting framework.

## Common Pitfalls

### Pitfall 1: Rate-Limit Check and Report Insert Race Across Requests (TOCTOU)

**What goes wrong:** Two nearly-simultaneous requests from the same identity both read the current count as "9 of 10", both pass the check, and both insert — silently allowing an 11th/12th request through the window that should have blocked the 11th.
**Why it happens:** A `SELECT COUNT(*)` followed by a separate `INSERT` is not atomic; under concurrent load (even at RoadTwin's modest v1 traffic, a single citizen double-tapping "submit" is enough to trigger this) the check-then-act pattern has a race window.
**How to avoid:** Wrap the rate-limit check + `SubmissionAttempt` insert + `Report` insert in a single database transaction, and consider a `SELECT ... FOR UPDATE` on a per-identity advisory lock row (or a Postgres advisory lock keyed on `identity_key`) if strict exactness matters more than simplicity. For v1 traffic volume, an off-by-one occasionally slipping through is an acceptable risk — but the transaction boundary itself (not necessarily the advisory lock) should exist from day one so the count and the insert can't diverge on a crash mid-request.
**Warning signs:** Load-testing with concurrent duplicate requests from one identity shows more successful submissions than the configured limit allows.

### Pitfall 2: Rate-Limit Table Grows Unbounded and Slows Every Check Query

**What goes wrong:** `submission_attempt` accumulates one row per request forever; after months of traffic, the `COUNT(*) WHERE created_at >= window_start` query — even though it's indexed — still has to scan a growing btree, and disk usage grows for data nobody needs past a few days.
**Why it happens:** It's easy to build the write path and the read (check) path and forget the table needs periodic pruning, since nothing in the initial implementation surfaces the growth problem until much later.
**How to avoid:** Index `created_at` (and the composite `(identity_key, created_at)` / `(ip_address, created_at)` pairs) from the first migration, and plan a cleanup step (even a manual `DELETE WHERE created_at < now() - interval '7 days'` cron/task, which can land in this phase or be explicitly flagged as a near-term follow-up) — don't let the table be the one place in the schema with no retention plan.
**Warning signs:** Table row count grows linearly with total historical traffic instead of plateauing near "traffic in the last N hours".

### Pitfall 3: GPS-Cooldown Check False-Positives on Legitimate Repeat Reporting

**What goes wrong:** Two different citizens (different device identities) happen to photograph the same visibly-worsening pothole from slightly different spots within the cooldown window and radius — the second, entirely legitimate report gets rejected with 429, which looks like a bug to the second citizen (INGT-01's "receive confirmation it was recorded" promise is broken for a real report).
**Why it happens:** D-05's cooldown rule is deliberately identity-agnostic (it catches "many rapid submissions clustered at one location" regardless of who submits them) — but that means it can't distinguish "one spammer submitting 20 times" from "20 different real citizens submitting once each within a few minutes of a genuinely bad pothole appearing."
**How to avoid:** Size `GPS_COOLDOWN_SECONDS` and `GPS_COOLDOWN_METERS` conservatively (short cooldown, tight radius — e.g., 5 minutes and 15 meters, not 1 hour and 100 meters) so it catches obvious bot/spam bursts without plausibly blocking distinct citizens reporting the same pothole minutes apart. Document the exact numbers chosen and the reasoning in the plan, since these are Claude's Discretion values with no user-specified target.
**Warning signs:** Any manual test where a second, clearly-different device/IP submitting a legitimate report near an existing one gets rejected.

### Pitfall 4: Signed Cookie Secret Missing or Defaulted in Production

**What goes wrong:** `device_id_cookie_secret` is left as a hardcoded default or empty string in `Settings`, meaning anyone can forge a valid signed device-id cookie by running the same signing code with the well-known default secret.
**Why it happens:** Following the existing `Settings` pattern (`database_url` has a working default for local dev), it's tempting to give `device_id_cookie_secret` a similar convenience default — but unlike a DB URL, a signing secret with a public default provides zero actual security.
**How to avoid:** Require `device_id_cookie_secret` from environment/`.env` with no safe default (raise at startup if unset, or generate an ephemeral random one for local dev only with a loud warning log, matching the existing `skeleton_routes_enabled` warning-log pattern in `backend/main.py`).
**Warning signs:** Grep for the literal secret value across environments; a signed cookie minted in local dev validating successfully against a different environment's secret indicates the default is shared/hardcoded.

### Pitfall 5: EXIF-GPS Fallback Silently Trusted Without the Map Confirmation Step

**What goes wrong:** A photo's embedded EXIF GPS is extracted and submitted directly as the Report's lat/lon without ever routing it through the Leaflet confirm/drag UI, violating D-10's "never silently submitted without visual confirmation" rule — and EXIF GPS can be stale (photo taken elsewhere, uploaded later) or entirely stripped by the phone's camera app/OS privacy settings, making it just as unreliable as a stale device GPS fix.
**Why it happens:** It's tempting to treat "we found GPS in the file" as a shortcut past the map-confirmation UX, since it feels like "the user already provided this."
**How to avoid:** Route EXIF-extracted GPS through exactly the same confirm/drag map UI as browser-Geolocation-derived coordinates — it is simply another candidate initial pin position, never an auto-submit path.
**Warning signs:** A code path exists where `image_path`-derived coordinates reach the `ReportCreate` payload without passing through the frontend's map-confirmation component first.

## Runtime State Inventory

Not applicable — this is a greenfield phase (new route file, new service package, new tables via a fresh Alembic migration), not a rename/refactor/migration phase. No existing runtime state (stored data, live service config, OS-registered state, secrets, or build artifacts) is being renamed or relocated.

## Code Examples

### 1. Browser Geolocation + Leaflet Confirm/Drag Marker (frontend)
```tsx
// Source: react-leaflet official "Draggable Marker" + "Events" examples
// (react-leaflet.js.org/docs/example-draggable-marker/,
//  react-leaflet.js.org/docs/example-events/), adapted for RoadTwin's
// auto-capture-then-confirm flow (D-10).
import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import type { LatLngLiteral } from "leaflet";

const DEFAULT_CENTER: LatLngLiteral = { lat: 0, lng: 0 }; // Claude's Discretion:
// pick a sensible city-level default for the deployment region.

function ClickToMove({ onMove }: { onMove: (pos: LatLngLiteral) => void }) {
  useMapEvents({
    click(e) {
      onMove(e.latlng);
    },
  });
  return null;
}

export function LocationPicker({
  onConfirm,
}: {
  onConfirm: (pos: LatLngLiteral, accuracy: number | null) => void;
}) {
  const [position, setPosition] = useState<LatLngLiteral>(DEFAULT_CENTER);
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const markerRef = useRef<L.Marker>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPosition({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setAccuracy(pos.coords.accuracy);
      },
      () => {
        /* denied/unavailable -- map stays at DEFAULT_CENTER for manual pin */
      },
    );
  }, []);

  const eventHandlers = useMemo(
    () => ({
      dragend() {
        const marker = markerRef.current;
        if (marker) setPosition(marker.getLatLng());
      },
    }),
    [],
  );

  return (
    <>
      <MapContainer center={position} zoom={16} style={{ height: 400 }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Marker
          draggable
          position={position}
          eventHandlers={eventHandlers}
          ref={markerRef}
        />
        <ClickToMove onMove={setPosition} />
      </MapContainer>
      <button onClick={() => onConfirm(position, accuracy)}>
        Confirm this location
      </button>
    </>
  );
}
```

### 2. Device-Identity Cookie Dependency (backend)
```python
# backend/routes/reports.py (excerpt)
# Source: itsdangerous docs pattern, applied to a FastAPI Response/Request
from fastapi import Cookie, Request, Response

from backend.services.ingestion.identity import COOKIE_NAME, read_or_mint_device_id


async def get_device_identity(
    response: Response,
    rt_device_id: str | None = Cookie(default=None),
) -> str:
    device_id, new_cookie_value = read_or_mint_device_id(rt_device_id)
    if new_cookie_value:
        response.set_cookie(
            key=COOKIE_NAME,
            value=new_cookie_value,
            httponly=True,
            secure=True,       # requires HTTPS in prod; relax only for local http dev
            samesite="lax",
            max_age=60 * 60 * 24 * 365,
        )
    return device_id
```

### 3. Full Route Composition (backend)
```python
# backend/routes/reports.py
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.repository import ReportRepository
from backend.db.session import get_session
from backend.schemas.report import ReportCreate, ReportRead
from backend.services.ingestion.rate_limit import enforce_rate_limits
from backend.services.ingestion.upload import (
    generate_object_key,
    put_report_image,
    validate_and_normalize_image,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportRead, status_code=201)
async def submit_report(
    request: Request,
    image: UploadFile,
    latitude: float = Form(...),
    longitude: float = Form(...),
    gps_accuracy_meters: float | None = Form(default=None),
    description: str | None = Form(default=None),
    device_id: str = Depends(get_device_identity),
    session: AsyncSession = Depends(get_session),
):
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limits(session, device_id, client_ip, latitude, longitude)

    normalized_bytes = await validate_and_normalize_image(image)

    payload = ReportCreate(
        latitude=latitude,
        longitude=longitude,
        gps_accuracy_meters=gps_accuracy_meters,
        description=description,
    )

    repo = ReportRepository(session)
    report = await repo.create(**payload.model_dump(exclude={"image_path"}))

    object_key = generate_object_key(report.id, "jpg")
    put_report_image(object_key, normalized_bytes, content_type="image/jpeg")
    await repo.update(report, image_path=object_key)

    await session.commit()
    return ReportRead.model_validate(report)
```

### 4. Client-Side Validate-Before-Submit (frontend, extends Phase 1's CR-01 pattern)
```ts
// frontend/src/api/client.ts (addition)
// Mirrors Phase 1's CR-01 lesson: never let an empty/invalid field silently
// coerce to a valid-looking value -- validate before firing the request.
export function validateReportDraft(draft: {
  latitude: number | null;
  longitude: number | null;
  imageFile: File | null;
}): string | null {
  if (draft.latitude === null || draft.longitude === null) {
    return "Please confirm a location on the map before submitting.";
  }
  if (draft.latitude < -90 || draft.latitude > 90) return "Invalid latitude.";
  if (draft.longitude < -180 || draft.longitude > 180) return "Invalid longitude.";
  if (!draft.imageFile) return "Please attach a photo of the damage.";
  return null;
}
```

### 5. MinIO Bucket Bootstrap (backend startup)
```python
# backend/main.py (addition, alongside existing skeleton-route mounting)
# Source: minio-py official examples pattern for idempotent bucket creation
from backend.services.ingestion.upload import minio_client, BUCKET

if not minio_client.bucket_exists(BUCKET):
    minio_client.make_bucket(BUCKET)
```

### 6. docker-compose MinIO Service Addition
```yaml
# docker-compose.yml (addition alongside the existing postgres service)
services:
  minio:
    image: minio/minio:latest
    container_name: roadtwin-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-roadtwin}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-roadtwin_dev_secret}
    ports:
      - "9000:9000"   # S3 API
      - "9001:9001"   # Web console
    volumes:
      - roadtwin_minio_data:/data
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  roadtwin_minio_data:
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| Direct-to-S3 presigned PUT from browser (common "modern" upload pattern) | Through-server multipart upload for RoadTwin specifically | Locked by D-07 for this project (not an industry-wide shift) | Server sees every byte before storage, enabling EXIF extraction and format/decompression-bomb validation the presigned-PUT pattern cannot do |
| Fixed-window rate-limit counters (`INCR` + TTL, Redis-idiomatic) | Rolling-window `COUNT(*) WHERE created_at >= window_start` (Postgres-idiomatic) | Driven by D-03's Postgres-not-Redis constraint | Avoids the classic fixed-window boundary-burst false-negative at the cost of a slightly heavier per-request query — acceptable at v1 traffic |
| Storing raw/unrotated images with orientation left to client-side CSS `image-orientation` | Server-side `ImageOps.exif_transpose()` normalization at upload time | Ongoing Pillow best practice, not a recent change | Guarantees every image is stored right-side-up regardless of which client (browser map viewer, future admin dashboard, future YOLO inference in Phase 3) renders it — YOLO inference in particular should not have to guess orientation |

**Deprecated/outdated:**
- Leaflet 2.0 remains alpha and must not be adopted (per CLAUDE.md and cross-checked npm registry: stable `leaflet` is still 1.9.4 as of this research date).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `itsdangerous` is the right signing library for the device-identity cookie (vs. a JWT, vs. Starlette's `SessionMiddleware`) | Standard Stack, Pattern 1 | Low — it's a small, swappable module; if the planner/user prefers a JWT-based approach instead, the interface (`read_or_mint_device_id`) stays the same and only the internals change. |
| A2 | Default numeric thresholds (10 req/identity/hr, 20 req/IP/hr, 15m/300s GPS cooldown, 10 MB max upload) are reasonable starting points for a citizen-reporting cadence | Pattern 2, Pattern 3, Pitfall 3 | Medium — these are genuinely guessed defaults (CONTEXT.md explicitly flags them as Claude's Discretion with "no user preference exists to anchor a specific number"); wrong values could either let spam through or block legitimate rapid reporting after a storm/major road event. The plan should treat these as configuration values, not hardcoded constants, so they're cheap to retune post-launch. |
| A3 | `Report.location`'s existing PostGIS geometry column can be queried directly with `ST_DWithin` for the GPS-cooldown check, without a new spatial column | Pattern 2 | Low — `backend/models/report.py` already defines this column with a spatial index; if GeoAlchemy2's exact function-wrapper syntax differs from the illustrative example, the fix is a syntax adjustment, not a design change. |
| A4 | No PyPI download-count signal is available to the package-legitimacy checker, making its `SUS` verdict on `minio`/`Pillow`/`python-multipart`/`itsdangerous` a tooling gap rather than real suspicion | Package Legitimacy Audit | Low — cross-verified independently via `pip index versions` (registry existence + version currency) and CLAUDE.md's own prior PyPI-JSON-API verification of the same packages; both align. |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Exact numeric rate-limit thresholds and GPS-cooldown radius/duration**
   - What we know: D-04/D-05 lock the *mechanism* (dual-key + spatial cooldown); CONTEXT.md explicitly defers the *numbers* to Claude's Discretion with no anchoring user preference.
   - What's unclear: What submission cadence is actually plausible for RoadTwin's target deployment (a single city pilot? Multiple neighborhoods?) — this affects whether 10/hour is generous or overly restrictive.
   - Recommendation: Ship with the defaults proposed in Pattern 2/3 above (10/identity/hr, 20/IP/hr, 15m/300s cooldown, 10 MB max), documented as configuration values in `Settings`, and flag in the plan that these are tunable without a schema change — this satisfies D-06's "must exist before real citizen traffic" without blocking on a number that can't be known precisely pre-launch.

2. **HEIC upload support scope**
   - What we know: CLAUDE.md's Claude's-Discretion note mentions "JPEG/PNG/HEIC" as a plausible allow-list; iPhone cameras default to HEIC.
   - What's unclear: Whether Pillow's stock build can decode HEIC without an additional plugin (`pillow-heif`) — Pillow's HEIF support depends on the platform's libheif availability and is not guaranteed out-of-the-box on every install.
   - Recommendation: Verify `Pillow`'s HEIF support at plan/execution time with a quick `Image.open()` smoke test against a real HEIC fixture; if unsupported, either add `pillow-heif` as an explicit dependency or narrow the v1 allow-list to JPEG/PNG only and document HEIC as a fast-follow, rather than silently failing every iPhone upload.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Docker | Running MinIO + Postgres locally via `docker-compose.yml` | ✓ | 29.8.0 (client) | — |
| PostgreSQL (via docker-compose) | Report persistence, rate-limit tables | ✓ (existing `postgis/postgis:16-3.4` service already defined) | 16 / PostGIS 3.4 | — |
| MinIO | Image object storage (INGT-04) | ✗ (no `minio` service in `docker-compose.yml` yet) | — | None viable — must be added in this phase's plan (Code Example §6); this is a hard requirement, not optional, per D-07/D-08/D-09. |
| Python 3.14 (host) / project venv | Backend execution | ✓ (`.venv` present; host Python 3.14.7) | 3.14.7 | Phase 1 already chose a 3.13 venv for asyncpg/psycopg wheel compatibility — confirm the existing `.venv` still targets 3.13, not the host 3.14, before adding new dependencies. |
| Node/npm | Frontend build (leaflet, react-leaflet install) | ✓ (npm registry reachable, versions confirmed live) | — | — |

**Missing dependencies with no fallback:**
- MinIO service is not yet present in `docker-compose.yml` — the plan must add it (see Code Example §6) before any upload-path task can be executed end-to-end.

**Missing dependencies with fallback:**
- None beyond the MinIO service addition above — all other dependencies are either already present or are pure-Python/npm packages installable via the existing package managers.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (backend, already configured — `pytest.ini`, `asyncio_mode = auto`); no frontend test framework exists yet |
| Config file | `pytest.ini` (backend); none for frontend |
| Quick run command | `pytest backend/tests/test_reports_ingestion.py -x` (new file, this phase) |
| Full suite command | `pytest` (from repo root; `testpaths = backend/tests`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| INGT-01 | POST /reports with valid image+GPS+timestamp persists a Report and returns 201 | integration | `pytest backend/tests/test_reports_ingestion.py::test_submit_report_success -x` | ❌ Wave 0 |
| INGT-01 | Missing/invalid GPS is rejected with 422 (server-side validation is sole authority, per Phase 1 CR-01 precedent) | unit | `pytest backend/tests/test_reports_ingestion.py::test_submit_report_invalid_gps -x` | ❌ Wave 0 |
| INGT-02 | First request without a device-id cookie receives a signed `Set-Cookie`; subsequent request with that cookie reuses the same identity | integration | `pytest backend/tests/test_ingestion_identity.py::test_device_id_mint_and_reuse -x` | ❌ Wave 0 |
| INGT-02 | Tampered/invalid signed cookie is rejected and a fresh identity is minted (not a 500) | unit | `pytest backend/tests/test_ingestion_identity.py::test_tampered_cookie_remints -x` | ❌ Wave 0 |
| INGT-03 | Nth request from the same identity within the window returns 429 with `Retry-After` | integration | `pytest backend/tests/test_rate_limit.py::test_identity_rate_limit_429 -x` | ❌ Wave 0 |
| INGT-03 | Nth request from the same IP (different identities) within the window returns 429 | integration | `pytest backend/tests/test_rate_limit.py::test_ip_rate_limit_429 -x` | ❌ Wave 0 |
| INGT-03 | Second submission within the GPS-cooldown radius/window returns 429 | integration | `pytest backend/tests/test_rate_limit.py::test_gps_cooldown_429 -x` | ❌ Wave 0 |
| INGT-04 | Successful submission's `image_path` resolves to a MinIO object retrievable via `presigned_get_object` | integration | `pytest backend/tests/test_upload.py::test_image_stored_and_retrievable -x` (marked `postgis`-style, requires docker-compose MinIO) | ❌ Wave 0 |
| INGT-04 | Oversized or malformed image upload is rejected (413/422), never silently truncated or stored | unit | `pytest backend/tests/test_upload.py::test_reject_oversized_and_corrupt_image -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest backend/tests/test_reports_ingestion.py backend/tests/test_ingestion_identity.py backend/tests/test_rate_limit.py backend/tests/test_upload.py -x`
- **Per wave merge:** `pytest` (full backend suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`; additionally, a manual smoke test against a real `docker-compose up` MinIO instance (not mocked) at least once before considering INGT-04 done, since `minio` SDK behavior against a mock vs. a real server can diverge on edge cases (bucket creation idempotency, presigned URL expiry format).

### Wave 0 Gaps
- [ ] `backend/tests/test_reports_ingestion.py` — covers INGT-01
- [ ] `backend/tests/test_ingestion_identity.py` — covers INGT-02
- [ ] `backend/tests/test_rate_limit.py` — covers INGT-03
- [ ] `backend/tests/test_upload.py` — covers INGT-04
- [ ] `backend/tests/conftest.py` fixture additions: a test MinIO client/bucket setup (either against a real docker-compose MinIO instance gated by a `minio`-style pytest marker analogous to the existing `postgis` marker, or a lightweight fake/mock for pure-unit tests) — decide during planning which tests need the real service vs. a mock.
- [ ] New Alembic migration `0003_ingestion_rate_limit_tables.py` must exist and be tested via the existing `test_migrations.py` pattern.
- [ ] `docker-compose.yml` MinIO service addition (Code Example §6) is itself a Wave 0 prerequisite — no upload test can run against a real backend without it.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|--------------------|
| V2 Authentication | No — explicitly no account system this phase (D-01/D-02) | N/A |
| V3 Session Management | Yes, in a narrow sense | The device-identity cookie is a lightweight session token, not a full authenticated session — apply V3's cookie-attribute controls (`HttpOnly`, `Secure`, `SameSite`) even though there's no login/logout lifecycle to manage |
| V4 Access Control | Minimal — no protected resources yet (that's Phase 7/AUTH-01..02) | Presigned GET URLs are the only access-control-adjacent concern: short expiry, never a permanent public link (D-09) |
| V5 Input Validation | Yes — primary control point for this phase | Pydantic v2 `ReportCreate` (already the sole validation authority per Phase 1's ASVS V5 docstring) extended with multipart form fields; Pillow validates the binary image payload separately, since Pydantic cannot validate binary file structure |
| V6 Cryptography | Yes | `itsdangerous`'s HMAC-based signing for the device-identity cookie — never hand-roll the signature comparison (timing-attack risk); the signing secret must come from environment config with no safe default (Pitfall 4) |
| V12 File and Resources (upload handling) | Yes — this phase's other primary control point | Format allow-list, max-size enforcement before full-body read, decompression-bomb guard, server-generated object keys (never client-supplied paths) — see Pattern 3 and its Anti-Patterns |

### Known Threat Patterns for {this stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Forged/replayed device-identity cookie to evade rate limiting | Spoofing | HMAC-signed cookie via `itsdangerous`; verify signature + max-age on every request; invalid signature → mint fresh identity, don't trust the claimed value |
| Decompression-bomb image upload (small file, huge decompressed pixel buffer) exhausting server memory/CPU | Denial of Service | Pillow `MAX_IMAGE_PIXELS` enforced as a hard error, plus a pre-check on raw upload byte size before any decode attempt |
| Path-traversal or object-overwrite via a client-supplied storage key/filename | Tampering | Server generates the MinIO object key from the Report's own server-side UUID; the request body never supplies a raw filename/path used directly as a storage key |
| Rate-limit bypass by rotating IP and clearing cookies simultaneously | Spoofing / repudiation of identity | Accepted residual risk for v1 per CONTEXT.md ("full bot/multi-IP resistance — CAPTCHA, proof-of-work — is explicitly NOT in scope for v1"); dual-key (D-04) raises the bar without claiming to fully close it — document this residual risk explicitly rather than implying the rate limiter is bulletproof |
| GPS spoofing to fabricate a damage pattern in a specific area to manipulate maintenance priority | Tampering | Out of scope for this phase's ingestion-time controls beyond the GPS-cooldown rule (D-05); PITFALLS.md flags this as a broader concern for the evidence-fusion phase (corroboration across independent identities), not solvable purely at ingestion |

## Project Constraints (from CLAUDE.md)

- Backend: FastAPI, PostgreSQL (PostGIS from day one), SQLAlchemy 2.0 async + GeoAlchemy2, Alembic migrations — all already established in Phase 1, extend rather than replace.
- Object storage: MinIO (S3-compatible) via Docker Compose, with presigned URLs — never permanent public URLs, never DB blobs.
- Do NOT introduce Redis or `arq` in this phase — explicitly reserved for Phase 3's inference queue.
- Do NOT introduce FastAPI `BackgroundTasks` for anything beyond truly trivial fire-and-forget work — this phase has no such need (no inference triggering happens here at all).
- Frontend: React 19 + Vite + TypeScript, Leaflet 1.9.x (not 2.0 alpha) + react-leaflet 5.x, React Query recommended (not mandated) for server-state — Phase 2's form/map state is simple enough that plain `useState`/`fetch` (matching Phase 1's existing `api/client.ts` pattern) is acceptable; introduce React Query only if the planner judges the form's async states (submit/loading/error) are getting unwieldy with plain hooks.
- Testing: pytest + pytest-asyncio (already configured) is the standard; extend with new test files per the Validation Architecture section above.
- GSD workflow enforcement: all file-changing work in this phase must flow through `/gsd-execute-phase` (per `.claude/CLAUDE.md`), not direct ad-hoc edits.

## Sources

### Primary (HIGH confidence)
- PyPI registry (`pip index versions`) — verified exifread 3.5.1, itsdangerous 2.2.0, minio 7.2.20, Pillow 12.3.0, python-multipart 0.0.32 — checked live 2026-09-23
- npm registry (`npm view`) — verified leaflet 1.9.4, react-leaflet 5.0.0 (+ peerDependencies), @types/leaflet 1.9.22 — checked live 2026-09-23
- Pillow official Security docs (pillow.readthedocs.io/en/stable/handbook/security.html) — MAX_IMAGE_PIXELS, DecompressionBombError, format allow-listing guidance
- minio-py official GitHub examples (github.com/minio/minio-py/blob/master/examples/presigned_get_object.py, presigned_put_object.py) — presigned-URL and put_object usage
- react-leaflet official docs (react-leaflet.js.org/docs/example-draggable-marker/, /example-events/) — draggable marker + useMapEvents pattern
- `.planning/research/PITFALLS.md` (this project's own prior research) — Pitfall 1 (ingestion-time anti-spam), Pitfall 2 (GPS accuracy), Anti-Pattern Cheat Sheet — directly informed Common Pitfalls and Architecture Patterns above
- `.planning/research/ARCHITECTURE.md` (this project's own prior research) — `routes/reports.py`/`services/` layout, Pattern 1 (async job queue — explicitly NOT built in this phase, referenced only for the boundary)
- CLAUDE.md Technology Stack section (this repository) — package/version pins for minio, Pillow, python-multipart, exifread, leaflet, react-leaflet

### Secondary (MEDIUM confidence)
- WebSearch: FastAPI Postgres-backed rate limiting without Redis (rolling-window vs. fixed-window pattern) — no single canonical library exists; pattern synthesized from general guidance, not copy-pasted from one authoritative source
- WebSearch: itsdangerous + FastAPI/Starlette signed-cookie session patterns — cross-referenced against Starlette's own `SessionMiddleware` source pattern
- WebSearch: exifread GPS tag extraction usage — cross-checked across exif-py's own docs and multiple independent blog examples showing consistent API usage

### Tertiary (LOW confidence)
- None flagged — all findings above either come from official docs/registries or are explicitly marked `[ASSUMED]` in the Standard Stack / Assumptions Log with reasoning for why the risk is low.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package/version pair verified live against PyPI/npm on research date, cross-checked against CLAUDE.md's own independently-verified stack doc.
- Architecture: MEDIUM-HIGH — the through-server-upload and signed-cookie patterns are well-established; the Postgres dual-key rate limiter + GPS cooldown is a hand-rolled design (no off-the-shelf library fits D-03's constraints), so its specific schema/query shape is this research's synthesis, not a borrowed canonical pattern.
- Pitfalls: MEDIUM-HIGH — directly extends this project's own prior `PITFALLS.md` research (Pitfall 1, 2) with phase-specific mechanics (TOCTOU on rate-limit checks, unbounded table growth, cooldown false-positives) reasoned from the locked design, not independently web-sourced for RoadTwin specifically.

**Research date:** 2026-09-23
**Valid until:** 30 days (stable stack; re-verify package versions if planning is delayed past late October 2026, especially Pillow given its frequent minor-version release cadence)
