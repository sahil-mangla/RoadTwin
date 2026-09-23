# Phase 2 — API Coverage Decision: MinIO Python SDK (`minio` 7.2.20)

**Decided:** 2026-09-23
**Detector:** `api-coverage.cjs` → `detected: true` (signals: `sdk`, `api`)
**Policy:** Full API coverage by default — INTEGRATE unless an explicit one-line opt-out reason is recorded.

This phase's only external service integration is the MinIO / S3-compatible object store
(`minio` Python SDK, locked by CLAUDE.md and CONTEXT.md D-07/D-08/D-09). The browser
Geolocation API (the detector's second signal) is a platform API, not a service SDK — its
surface is a single call (`navigator.geolocation.getCurrentPosition`) already fully covered by
D-10's confirm/drag flow, so it needs no coverage table.

## Capability Table

| SDK Capability | Decision | Where / Reason |
|---|---|---|
| `Minio(endpoint, access_key, secret_key, secure)` | INTEGRATE | `backend/services/ingestion/upload.py` module-level client built from `Settings.minio_*`. |
| `bucket_exists(bucket)` | INTEGRATE | Startup bootstrap in `backend/main.py`; also the `minio_available` pytest fixture's reachability probe. |
| `make_bucket(bucket)` | INTEGRATE | Idempotent startup bootstrap (only when `bucket_exists` is false). |
| `put_object(bucket, key, data, length, content_type)` | INTEGRATE | The through-server upload write path (D-07/D-08). |
| `presigned_get_object(bucket, key, expires)` | INTEGRATE | `GET /api/reports/{id}/image-url` short-lived retrieval (D-09). |
| `stat_object(bucket, key)` | INTEGRATE | Existence/size assertion in `test_upload.py::test_image_stored_and_retrievable`, and the pre-put collision guard that protects stored evidence from overwrite. |
| `get_object(bucket, key)` | INTEGRATE | Byte-level round-trip assertion in `test_upload.py` (proves the stored object is the normalized image, not a truncated body). |
| `remove_object(bucket, key)` | OPT-OUT | Images are permanent evidence tied to a longitudinal RoadObservation history (CLAUDE.md retention model); no deletion path exists in v1, and `must_haves.prohibitions` forbids destroying stored evidence. |
| `remove_objects(bucket, keys)` | OPT-OUT | Same reason as `remove_object` — bulk deletion is strictly further from the retention model. |
| `list_objects(bucket, prefix)` | OPT-OUT | All image access is addressed through the `Report.image_path` key (INGT-04); a bucket listing would be an out-of-band enumeration path with no consumer. |
| `list_buckets()` | OPT-OUT | Exactly one bucket (`Settings.minio_bucket`) exists; enumeration has no consumer. |
| `remove_bucket(bucket)` | OPT-OUT | Destroys all stored evidence — never invoked by application code. |
| `fput_object` / `fget_object` | OPT-OUT | Filesystem-path variants; this phase never writes the upload to local disk (bytes stay in memory between Pillow validation and `put_object`). |
| `copy_object` / `compose_object` | OPT-OUT | No server-side object duplication or multipart composition in v1; one report yields exactly one object. |
| `presigned_put_object` / `presigned_post_policy` | OPT-OUT | Direct browser→MinIO upload is explicitly rejected by D-07 (the server must see the bytes to run Pillow validation and EXIF extraction). |
| `get_presigned_url(method, ...)` | OPT-OUT | The typed `presigned_get_object` helper covers the only retrieval need; the generic form adds a method parameter with no caller. |
| `set_bucket_policy` / `get_bucket_policy` | OPT-OUT | A bucket policy granting anonymous read is exactly what D-09 forbids; the bucket stays private and access flows only through presigned GETs. |
| `set_bucket_versioning` | OPT-OUT | Deferred — object keys are `reports/{report_uuid}.{ext}`, unique per report, so no version history is needed; the overwrite prohibition is enforced in application code via `stat_object`. |
| `set_bucket_lifecycle` | OPT-OUT | Deferred — conflicts with the permanent-evidence retention model; revisit only if a retention policy is ever adopted. |
| `set_bucket_encryption` / SSE-C params | OPT-OUT | Deferred to deployment hardening; local dev MinIO has no KMS. Recorded in `<threat_model>` as an accepted low-severity residual for v1. |
| `set_object_tags` / `get_bucket_tags` | OPT-OUT | Report metadata lives in Postgres (the system of record); duplicating it as object tags would create a second, drift-prone copy. |
| `select_object_content` | OPT-OUT | S3 Select applies to structured data objects (CSV/JSON/Parquet), not JPEG/PNG images. |
| `listen_bucket_notification` | OPT-OUT | Event-driven post-upload processing is Phase 3's async perception pipeline (arq/Redis), explicitly out of this phase's boundary. |

## Rollup

- **INTEGRATE:** 7 capabilities
- **OPT-OUT:** 17 capabilities, each with a recorded reason above
- **Net-new dependency:** `minio>=7.2.20,<7.3` (legitimacy-audited in `02-RESEARCH.md`, human-verified in plan `02-01` task 1)
