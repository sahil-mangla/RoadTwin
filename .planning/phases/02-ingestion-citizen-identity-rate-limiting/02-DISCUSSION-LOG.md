# Phase 2: Ingestion, Citizen Identity & Rate Limiting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-22
**Phase:** 2-Ingestion, Citizen Identity & Rate Limiting
**Mode:** `--auto` (fully autonomous — no AskUserQuestion calls, single pass)
**Areas discussed:** Citizen identity mechanism, Rate limiting & anti-spam, Image upload path, GPS capture UX, Code organization

---

## Citizen Identity Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Cookie-based device/session ID | Server-issued HttpOnly cookie, zero citizen input required | ✓ |
| Unverified free-text email | Citizen types an email, stored as identity anchor, never verified | |
| Both | Cookie as primary + optional email as secondary signal | |

**Selected:** Cookie-based device/session ID (D-01, D-02)
**Notes:** INGT-02 reads "device/session ID **or** email" — the "or" means one mechanism is sufficient. Cookie wins on frictionlessness; an unverified email field adds a form field with no real identity-strength benefit over the cookie. Full account system is explicitly out of scope per REQUIREMENTS.md.

---

## Rate Limiting & Anti-Spam Backend

| Option | Description | Selected |
|--------|-------------|----------|
| Redis-backed counter | Sliding window / token bucket in Redis | |
| Postgres-backed counter | Simple counter/window table in the already-live Postgres | ✓ |
| In-memory / process-local counter | No shared state | |

**Selected:** Postgres-backed counter (D-03)
**Notes:** Phase 1's D-04 already sequenced Redis to arrive in Phase 3 (for `arq`'s inference queue). Phase 2's own scope never enqueues a background job — see the explicit domain-boundary note in CONTEXT.md — so pulling Redis forward a phase early isn't justified. In-memory was rejected outright: doesn't survive restarts or work across multiple workers.

## Rate Limiting Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Identity-cookie only | Key solely on the device cookie | |
| Identity-cookie + IP | Whichever is closer to its limit governs | ✓ |
| IP only | Ignore the identity cookie | |

**Selected:** Identity-cookie + IP (D-04), plus a same-GPS-point submission cooldown (D-05)
**Notes:** `research/PITFALLS.md` line 40 flags that no account/device-level rate telemetry existing at all is a real gap; a cookie-only limiter is trivially bypassed by clearing cookies, so IP is added as a second signal. PITFALLS.md line 35 separately recommends a StreetBump-style minimum-time-between-reports-at-the-same-point cooldown, which catches a different spam shape (many rapid nearby submissions) than identity throttling alone. Full bot/multi-IP resistance (CAPTCHA, proof-of-work) is explicitly out of scope for v1.

---

## Image Upload Path

| Option | Description | Selected |
|--------|-------------|----------|
| Through-server multipart upload | Citizen POSTs image to FastAPI; server validates, extracts EXIF, writes to MinIO | ✓ |
| Direct-to-MinIO presigned PUT | Browser uploads straight to MinIO using a presigned URL from the API | |

**Selected:** Through-server multipart upload (D-07, D-08, D-09)
**Notes:** CLAUDE.md's stack doc names `python-multipart` and `Pillow`/`exifread` specifically for "EXIF GPS extraction on upload" — that only works if the server receives the actual image bytes, which a presigned-PUT handoff bypasses. Retrieval still uses short-lived presigned GET URLs per the same stack doc.

---

## GPS Capture UX

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-capture, submit silently if successful | No confirmation step when geolocation succeeds | |
| Auto-capture, always show on map for confirm/adjust before submit; manual pin on failure | Single unified confirmation UI for both paths | ✓ |
| Manual pin only (no auto-capture attempt) | Ignores the "auto-captured" half of INGT-01 | |

**Selected:** Auto-capture with always-shown map confirmation (D-10)
**Notes:** INGT-01 requires supporting both auto and manual GPS. Never trusting a raw auto-capture without a visual confirmation step avoids silently submitting a wrong location (e.g., stale cached fix) and gives one code path instead of two divergent ones.

## Low-Accuracy GPS Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Hard-reject below an accuracy threshold | Refuse to persist a Report with poor GPS accuracy | |
| Accept and flag | Persist as normal; surface a non-blocking "may be imprecise" hint | ✓ |

**Selected:** Accept and flag (D-11)
**Notes:** INGT-01 promises the citizen "receive confirmation it was recorded." Rejecting a legitimate submission over ordinary mobile GPS noise breaks that promise. `gps_accuracy_meters` already exists on `Report` (Phase 1) specifically so downstream clustering/evidence-fusion can discount noisy points later, per PITFALLS.md's Pitfall 2 guidance.

---

## Code Organization

| Option | Description | Selected |
|--------|-------------|----------|
| Extend `routes/skeleton.py` with real citizen endpoints | Reuse Phase 1's diagnostic router | |
| New `routes/reports.py` + new `services/ingestion/` | Separate real citizen-facing code from Phase 1's diagnostic tooling | ✓ |

**Selected:** New `routes/reports.py` + `services/ingestion/` (D-12, D-13, D-14)
**Notes:** `research/ARCHITECTURE.md`'s suggested layout names `routes/reports.py` explicitly. Keeping `skeleton.py` as internal-only diagnostic tooling (its stated purpose since Phase 1) avoids mixing real citizen-facing behavior into a file meant for schema-status/chain-seed debugging.

---

## Claude's Discretion

- Exact rate-limit numeric thresholds (requests/hour per identity, GPS-point cooldown radius/duration)
- Exact device-identity cookie name, expiry, and signing approach
- Exact Postgres rate-limit table schema
- Exact image format/size allow-list
- Exact "imprecise location" accuracy threshold for the UI hint
- Leaflet default map center/zoom when no GPS is available at all

## Deferred Ideas

None — `--auto` mode ran as a single autonomous pass with no live user turn to surface scope-creep tangents. The one boundary worth restating: async YOLO inference triggering and arq/Redis worker setup belong to Phase 3, not this phase.
