# RoadTwin

RoadTwin is a predictive road-health and maintenance-intelligence system.
Citizens submit geotagged photos of road damage; a YOLOv8/RDD2022
perception layer detects the damage, and RoadTwin fuses those observations
over time into per-road-segment health profiles — tracking condition,
deterioration rate, and future risk — to produce an explainable, ranked
maintenance queue for road authorities.

## Prerequisites

- Docker (for the PostgreSQL + PostGIS and MinIO services)
- Python 3.12+
- Node 20+

## Run the full stack locally

1. `docker compose up -d` — brings up both Postgres+PostGIS and MinIO. The
   MinIO console is at http://localhost:9001 (dev credentials: `roadtwin` /
   `roadtwin_dev_secret`, overridable via `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`).
2. `pip install -r backend/requirements-dev.txt`
3. Copy `backend/.env.example` to `backend/.env` and set `DEVICE_ID_COOKIE_SECRET`
   — without it, device identities (the cookie citizens are attributed by)
   do not survive a backend restart.
4. `alembic -c backend/alembic.ini upgrade head`
5. In two parallel terminals:
   - `uvicorn backend.main:app --reload --port 8000`
   - `npm --prefix frontend install && npm --prefix frontend run dev`

Then open http://localhost:5173.

## Run the tests

```
pytest backend/tests/ -v
```

## Operational notes (Phase 2: ingestion, identity & rate limiting)

- **Image storage**: MinIO's official Docker image was withdrawn from
  Docker Hub in 2026; `docker-compose.yml` uses the community-maintained
  `coollabsio/minio` image as a drop-in replacement (see the comment on
  that service block). Uploaded images are stored as-is (byte-identical
  unless EXIF orientation requires a rotation) and are only ever reachable
  through a presigned URL that expires after `minio_presigned_url_ttl_seconds`
  (900s / 15 minutes by default) — no permanently public image URL exists.
- **Accepted image formats**: JPEG and PNG. HEIC is not decodable by this
  environment's stock Pillow build and is explicitly rejected with a 422
  naming the unsupported format, rather than silently failing every iPhone
  upload.
- **Rate limiting**: best-effort anti-spam, not a security boundary — it
  can be bypassed by clearing cookies while rotating IP. Two independent
  rolling-window counters (device identity and client IP, default 10/hour
  and 20/hour) plus a spatial cooldown (default 15m / 300s) all live in
  `backend/core/config.py`'s `Settings` and are retunable via environment
  variables with no schema change.
- **`submission_attempt` retention**: rows are pruned by
  `backend.services.ingestion.rate_limit.prune_old_attempts`, which deletes
  rows older than `submission_attempt_retention_days` (7 days by default).
  This is a callable, tested operation — it is **not yet scheduled**; wiring
  it to a periodic job belongs with Phase 3's background-worker
  infrastructure (`arq`/Redis), which this phase deliberately does not
  introduce.

## Project status

Phase 1 shipped a **Walking Skeleton** — the seven-entity data contract
(Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction,
MaintenanceRecommendation) locked and proven reachable end-to-end
(browser → FastAPI → Postgres/PostGIS → browser) through a minimal skeleton
page and API. See
`.planning/phases/01-schema-core-data-contracts/01-SKELETON.md` for what
was deliberately out of scope in that phase.

Phase 2 adds the real citizen ingestion path: `POST /api/reports` accepts a
photo plus coordinates, stores the image in MinIO, attributes the
submission to a signed device-identity cookie (no account, no email), and
protects against spam via rate limiting and a GPS-proximity cooldown. No
perception (YOLO detection), clustering, evidence fusion, health scoring,
forecasting, or priority scoring exists yet.

## Perception worker (Phase 3)

Inference runs in a background `arq` worker, never in the upload request.

1. `docker compose up -d redis`
2. `pip install -r backend/requirements-ml.txt` (install a torch build for your machine first).
3. Download YOLOv8 weights trained on RDD2022 (e.g. from Kaggle) and set `YOLO_WEIGHTS_PATH=/path/to/best.pt` in `backend/.env`.
4. `arq backend.worker.WorkerSettings` from the repo root.

Without a worker running, submissions still succeed and stay `perception_status=pending`.
