# Phase 2: Ingestion, Citizen Identity & Rate Limiting - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the real citizen-facing report-submission pipeline: a durable `POST /reports`-style endpoint that accepts an image + GPS (auto-captured or manual pin) + timestamp + optional description, attributes the submission to a lightweight (non-account) identity, enforces rate limiting to block spam/evidence-score gaming, and stores the uploaded image in object storage with a reference on the `Report` record.

**Explicit lower boundary (does NOT belong here):** This phase ends at "Report safely persisted, image in object storage, request confirmed to the citizen." It does NOT enqueue, trigger, or scaffold YOLO inference, arq/Redis workers, or any async job queue — that is Phase 3 (Async Perception Pipeline, PERC-01..03), which explicitly depends on this phase. Do not pull Phase 3's worker infrastructure forward.

**Explicit upper boundary:** No full account system (email/password, OAuth, profile/history) — explicitly out of scope per REQUIREMENTS.md's Out-of-Scope table ("lightweight identity is sufficient for v1"). No moderation UI (MODR-01 is v2).

This is an auto-mode (`--auto`) discussion pass: no live user turn occurred. Every decision below was resolved autonomously using the recommended default for its gray area, grounded in REQUIREMENTS.md's exact wording, ROADMAP.md's Phase 2 success criteria, the locked tech stack (CLAUDE.md), and `research/PITFALLS.md`'s explicit ingestion-time guidance. Flagged inline for audit.

</domain>

<decisions>
## Implementation Decisions

### Citizen Identity (INGT-02)

- **D-01:** Lightweight identity = a server-issued device/session identifier persisted as an HttpOnly cookie, generated on first visit if absent. This alone satisfies INGT-02's "device/session ID **or** email" wording. *(recommended default — the "or" phrasing means one mechanism is sufficient; a cookie ID needs zero citizen input, keeping submission frictionless, whereas an unverified free-text email field adds surface area with no v1 identity-strength benefit.)*
- **D-02:** No email-capture field is built in this phase. If evidence-fusion (Phase 5) later needs a stronger identity signal, that is a new gray area for that phase, not a Phase 2 concern.

### Rate Limiting & Anti-Spam (INGT-03)

- **D-03:** Rate-limit state lives in **Postgres** (a simple counter/window table), not Redis. *(recommended default — Phase 1's D-04 already sequenced Redis's introduction to Phase 3, when `arq` needs it for the inference queue. Phase 2's own scope, per Architecture research, does not enqueue any background job — see the domain boundary above — so introducing Redis a phase early is unnecessary infrastructure. Postgres is already live from Phase 1.)*
- **D-04:** Rate limiting keys on **both** the device-identity cookie (D-01) **and** the client IP — whichever is closer to its limit governs. *(recommended default — a cookie-only limiter is trivially bypassed by clearing cookies; per `research/PITFALLS.md` line 40, "No account/device-level submission-rate telemetry exists" was flagged as a gap. Full bot/multi-IP resistance — CAPTCHA, proof-of-work — is explicitly NOT in scope for v1.)*
- **D-05:** In addition to identity-rate limiting, add a **minimum time-between-reports for the same GPS point** (a StreetBump-style submission cooldown), per `research/PITFALLS.md`'s explicit recommendation (line 35). This catches a distinct spam pattern (many rapid submissions clustered at one location) that per-identity throttling alone doesn't.
- **D-06:** Exceeding either limit returns **HTTP 429 with a clear retry-after value** — never a silent drop, per PITFALLS.md's Anti-Pattern Cheat Sheet ("must exist before real citizen traffic," not a stub).
- Exact numeric thresholds (requests/hour, cooldown radius/duration) are Claude's Discretion (see below) — no user preference exists to anchor a specific number.

### Image Upload Path (INGT-04)

- **D-07:** Upload flows **through the FastAPI server** (multipart `UploadFile`), not a direct-to-MinIO presigned PUT from the browser. *(recommended default — CLAUDE.md's stack doc specifically lists `python-multipart` + `Pillow`/`exifread` "to auto-populate geolocation from an uploaded photo's EXIF metadata when the citizen doesn't manually drop a pin," which requires the server to actually receive and inspect the image bytes — incompatible with a blind presigned-PUT handoff.)*
- **D-08:** After receiving and validating the upload (format/size — see Claude's Discretion), the server writes it to MinIO and persists the object key on `Report` (the `image_path`-shaped column already exists from Phase 1 — Plan 01-03/01-05's code review flagged it as unvalidated `str`; this phase is where it becomes load-bearing and should gain real constraints: max length, allow-listed key pattern, no client-supplied paths).
- **D-09:** Retrieval uses **short-lived presigned GET URLs**, never permanent public URLs, per CLAUDE.md's storage guidance.
- Content-based validation ("does this photo actually show a road") is explicitly **not** this phase's job — `research/PITFALLS.md` line 196 defers that to YOLO's own no-detection case in Phase 3. Phase 2 validates format/size only.

### GPS Capture UX (INGT-01)

- **D-10:** Attempt the browser Geolocation API automatically on page load. Whether it succeeds or fails, the result is always shown on a Leaflet map for the citizen to **confirm or drag-adjust before submitting** — a raw auto-captured coordinate is never silently submitted without visual confirmation. On failure/denial, the map simply starts at a default view and the citizen places the pin manually. One unified confirmation UI covers both the auto and manual paths.
- **D-11:** A submission with poor GPS accuracy is **accepted and flagged, never hard-rejected** at ingestion. *(recommended default — INGT-01 promises the citizen "receive confirmation it was recorded"; rejecting a real submission because of ordinary mobile GPS noise breaks that promise. `gps_accuracy_meters` already exists on `Report` from Phase 1 specifically so downstream clustering/evidence-fusion can discount noisy points — per `research/PITFALLS.md`'s Pitfall 2 guidance — rather than ingestion silently dropping legitimate reports.)* A non-blocking "location may be imprecise" UI hint above some accuracy threshold is Claude's Discretion to size.

### Code Organization

- **D-12:** New citizen-facing route file: `backend/routes/reports.py` — the real `POST /reports` (and related) endpoints. Phase 1's `backend/routes/skeleton.py` is internal diagnostic tooling and stays untouched; do not extend it with real citizen-facing behavior. *(directly matches `research/ARCHITECTURE.md`'s suggested layout, which names `routes/reports.py` explicitly as "POST report (sync ingestion)".)*
- **D-13:** New `backend/services/ingestion/` package for identity/rate-limit/upload logic — parallel to the `spatial/`, `intelligence/`, `maintenance/` stub packages Phase 1 already created. Ingestion wasn't stubbed in Phase 1 because Phase 1 was schema-only; this is its first real service module.
- **D-14:** New frontend page for the real citizen report form (not `SkeletonPage.tsx`, which stays as Phase 1's internal diagnostic tool). Reuse the established `api/client.ts` fetch-client pattern and form-validation lesson from Phase 1's code review (CR-01: never let an empty/invalid numeric field silently coerce to a valid-looking value — validate before submit, same as the Phase 1 fix).

### Claude's Discretion

- Exact rate-limit numbers (requests per identity per hour; GPS-point cooldown radius and duration) — no user preference exists; planner/research should size against a plausible citizen-reporting cadence, not guess arbitrarily.
- Exact cookie name, expiry, and signing approach for the device-identity token.
- Exact Postgres rate-limit table schema (single shared counter table vs. one per limiter).
- Exact image size/format allow-list (e.g., JPEG/PNG/HEIC, max MB) — CLAUDE.md's stack doc references this generically ("size limits") without a specific number.
- Exact "imprecise location" accuracy threshold (D-11) for the non-blocking UI hint.
- Leaflet default map center/zoom when GPS is unavailable and the citizen must place a pin from scratch.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` §Ingestion (INGT-01..04) — this phase's requirements, and §Trust & Moderation (MODR-01, v2, confirms `rejected` status stays unused this phase) and §Out of Scope (confirms no full account system)
- `.planning/ROADMAP.md` Phase 2 section — goal and success criteria this phase must satisfy; Phase 3 section — confirms the inference-queue boundary this phase must NOT cross
- `.planning/reference/RoadTwin-Architecture-Input-Spec.md` §5 (Input Specification) — confirms which fields are citizen-supplied vs. system-generated (timestamp is system-generated, not citizen input)

### Research (already-locked technical guidance for this phase)
- `.planning/research/PITFALLS.md` Pitfall 1 (lines 25-43) — ingestion-time anti-spam filters, rate limiting per device/account, GPS-point submission cooldowns; directly informs D-03..D-06
- `.planning/research/PITFALLS.md` Pitfall 2 (lines 46-65) — GPS accuracy capture/weighting; directly informs D-10..D-11
- `.planning/research/PITFALLS.md` line 196 (Image upload/storage pitfall) — content validation deferred to Phase 3's YOLO no-detection case, not this phase
- `.planning/research/PITFALLS.md` Anti-Pattern Cheat Sheet (line 186) — rate limiting "must exist before real citizen traffic," not a deferrable stub
- `.planning/research/ARCHITECTURE.md` lines 95-111 — suggested `routes/reports.py`, `services/` layout; directly informs D-12..D-13
- `.planning/research/ARCHITECTURE.md` "Pattern 1: Async Job Queue for ML Inference" (lines 122-136) — shows the `enqueue_inference.delay(...)` call as part of the reports route example; this phase implements everything in that example EXCEPT the enqueue call, which belongs to Phase 3
- `CLAUDE.md` Technology Stack — MinIO + presigned URLs, `python-multipart`/`Pillow`/`exifread` for upload handling, Redis reserved for `arq` (Phase 3)

### Phase 1 carry-forward
- `.planning/phases/01-schema-core-data-contracts/01-CONTEXT.md` D-04 — Redis/MinIO phase sequencing (MinIO lands now; Redis stays deferred to Phase 3)
- `.planning/phases/01-schema-core-data-contracts/01-REVIEW.md` WR-02 — `ReportCreate.image_path` is currently unvalidated; this phase is where it must gain real constraints (D-08)
- `backend/models/report.py`, `backend/schemas/report.py` — the existing `Report` entity/contract this phase writes real rows into (no new entity, no schema migration expected)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/db/repository.py` — `BaseRepository`/`MutableRepository`/`ReportRepository` pattern already established; a rate-limit counter table and any new ingestion tables should follow the same repository split.
- `backend/core/config.py` — `Settings`/`pydantic-settings` pattern already holds DB URLs; extend with MinIO endpoint/credentials here, not a new config module.
- `backend/main.py` — FastAPI app + router-mounting pattern already established (`skeleton.py` is mounted here); `reports.py` mounts the same way.
- `frontend/src/api/client.ts`, `frontend/src/types.ts` — typed fetch-client pattern already established in Phase 1; extend rather than duplicate.

### Established Patterns
- Repository mutability split (mutable vs. append-only) — Phase 1's core pattern; a rate-limit counter is mutable (increments), fits `MutableRepository`.
- Pydantic v2 contracts mirrored 1:1 with route input — `ReportCreate` already exists and already has `latitude`/`longitude`/`gps_accuracy_meters`/`description`/`image_path`; this phase's route should use/extend this existing schema, not invent a parallel one.
- Client-side validate-before-submit (Phase 1 CR-01 fix) — the real citizen form must not repeat the empty-string-coerces-to-a-valid-value mistake.

### Integration Points
- New `routes/reports.py` mounts into the existing `backend/main.py` app alongside `routes/skeleton.py`.
- New citizen-facing frontend page is a sibling to `SkeletonPage.tsx`, added to whatever router/nav Phase 1's `App.tsx` currently uses (single-page today — this phase likely introduces real routing/navigation for the first time).

</code_context>

<specifics>
## Specific Ideas

No specific implementation examples were provided beyond what's captured in REQUIREMENTS.md, ROADMAP.md, and the research files cited above — this was a fully autonomous (`--auto`) pass with no live user input; open to standard FastAPI/React conventions for anything not explicitly decided.

</specifics>

<deferred>
## Deferred Ideas

None — no live user turn occurred to surface scope-creep tangents (`--auto` mode). The one boundary worth restating here (not a deferred *idea*, a deferred *dependency*): async YOLO inference triggering and arq/Redis worker setup belong to Phase 3, not here — see the domain boundary above.

</deferred>

---

*Phase: 2-Ingestion, Citizen Identity & Rate Limiting*
*Context gathered: 2026-09-22*
