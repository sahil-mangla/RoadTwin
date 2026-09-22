<!-- GSD:project-start source:PROJECT.md -->

## Project

**RoadTwin**

RoadTwin is a predictive road-health and maintenance-intelligence system. Citizens submit geotagged photos of road damage; a YOLOv8/RDD2022 perception layer detects the damage, and RoadTwin fuses those observations over time into per-road-segment health profiles — tracking condition, deterioration rate, and future risk — to produce an explainable, ranked maintenance queue for road authorities.

**Core Value:** YOLO detects what is visible; RoadTwin determines what the road's condition means, how it is changing, what may happen next, and what should be fixed first. The road segment — not the individual report — is the primary intelligence entity.

### Constraints

- **Tech stack**: React/Vite frontend, FastAPI backend, PostgreSQL (SQLite acceptable for dev), Leaflet for maps, YOLOv8 + RDD2022 weights for perception — fixed by prior design, not open for re-litigation
- **Build order**: Schemas/data contracts must be locked before intelligence-layer code is written; perception and raw-detection persistence come before clustering; clustering before segments; segments before health scoring; health scoring before deterioration; deterioration before forecasting; forecasting before priority scoring; priority scoring before the authority dashboard is built around it — per the spec's Implementation Order
- **Forecasting approach**: v1 must use a transparent, explainable trend-estimation method — no deep-learning forecasting model until enough longitudinal RoadObservation data has been collected to justify it
- **External data**: Traffic, weather, road classification, repair history, and proximity-to-vulnerable-locations are enhancement inputs only — never required for the core pipeline to function

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Context

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | >=0.115, latest stable 0.141.1 | Backend API framework | Already locked by PROJECT.md. Async-native, Pydantic-integrated, auto OpenAPI docs — the de facto standard for Python ML-serving backends in 2025/2026. |
| Pydantic | v2, >=2.7, latest 2.13.5 | Request/response validation, data contracts | FastAPI 0.141.x requires Pydantic v2 (pydantic-core Rust engine, 3–50x faster than v1). Use Pydantic models directly as the schema layer for Report/Detection/RoadSegment/RoadObservation/RoadHealth/Prediction/MaintenanceRecommendation contracts — PROJECT.md requires these schemas locked *before* intelligence-layer code is written, and Pydantic is the natural place to lock them. |
| Uvicorn | latest 0.5x, run with `--workers` via Gunicorn in prod | ASGI server | Standard FastAPI production server. Use `uvicorn[standard]` for dev; front with Gunicorn+UvicornWorker (or just multiple uvicorn workers behind a reverse proxy) in prod. |
| React | 19.x (latest 19.3.0) | Frontend UI | Locked by PROJECT.md. React 19 is required as a peer dependency by react-leaflet 5.x (see Mapping below), so this isn't optional — pin to React 19. |
| Vite | 6.x-8.x (latest 8.3.0) | Frontend build tool | Locked by PROJECT.md. Fast HMR, native ESM, minimal config vs CRA/webpack. |
| TypeScript | latest 5.x | Frontend type safety | Not explicitly mandated but the de facto default for any new Vite+React project in 2025/2026; strongly recommended given the number of typed entities (7 core data model entities) flowing frontend↔backend. |

### Database & ORM

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 15+ (16/17 fine) | Primary datastore | Locked by PROJECT.md. Needed for PostGIS extension in production; SQLite acceptable for local dev only. |
| PostGIS | 3.4+ (matches PG version) | Spatial extension | Required once you move past ad-hoc lat/lon columns — provides `ST_ClusterDBSCAN`, `ST_DWithin`, spatial indexes (GiST). Not strictly required on day one (raw lat/lon + scikit-learn DBSCAN works fine to start), but install it from the beginning so the schema migration path is trivial later. |
| SQLAlchemy | 2.0.x (latest 2.0.54), async mode | ORM | The standard Python ORM; 2.0's async engine (with `asyncpg` driver) pairs naturally with FastAPI's async request handlers, avoiding blocking DB calls in the event loop. |
| GeoAlchemy2 | latest 0.20.0 | Spatial ORM extension | Wraps PostGIS geometry columns and functions (`ST_DWithin`, `ST_ClusterDBSCAN`, etc.) as SQLAlchemy expressions — lets clustering/segment-aggregation queries live in typed Python instead of raw SQL strings. |
| asyncpg | latest 0.31.0 | Async Postgres driver | Fastest async driver for SQLAlchemy 2.0 async engine + Postgres. (Use `psycopg[binary]` sync driver only for Alembic migrations, which run sync by convention.) |
| Alembic | latest 1.20.0 | DB migrations | Standard SQLAlchemy migration tool. Given PROJECT.md's hard requirement that schemas/data contracts be locked before intelligence-layer code, treat every entity change as an Alembic migration from commit one — don't hand-edit schema. |

### ML / Perception Layer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ultralytics | latest 8.4.158 | YOLOv8 model loading + inference | The official package for YOLOv8 (also ships v9–v12 under the same API, but PROJECT.md specifies YOLOv8/RDD2022 weights specifically). `pip install ultralytics`; requires Python>=3.8, PyTorch>=1.8. |
| PyTorch | 2.x (CPU or CUDA build matching your deploy target) | Backend tensor runtime for ultralytics | Required by `ultralytics`. Use the CPU wheel for local dev / small deployments; CUDA wheel only if you have GPU inference infrastructure — RDD2022-scale YOLOv8n/s models run acceptably on CPU for a crowdsourced-report volume (not a live video stream). |
| Pillow | latest | Image decode/preprocessing | Standard image I/O; `ultralytics` uses it internally, but you'll also need it directly for thumbnailing/EXIF-GPS extraction on upload. |

### Geospatial Clustering

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| scikit-learn | latest 1.9.1 | `DBSCAN` clustering (duplicate-report merge + point→segment aggregation) | **Recommended starting point** — matches PROJECT.md's explicit "DBSCAN starting point" requirement. Runs in-process on a coordinate array pulled from the DB; trivial to unit-test in isolation; no extra infra. Use the haversine metric (`sklearn.cluster.DBSCAN(metric='haversine', eps=radius_in_radians, min_samples=...)`) since lat/lon is not Euclidean. |
| PostGIS `ST_ClusterDBSCAN` | (ships with PostGIS 3.x) | Alternative/future clustering path | Runs the same DBSCAN algorithm inside SQL over geometry columns — no Python export round-trip, and composes naturally with other spatial joins (e.g., "cluster within this road corridor"). **Defer to this once clustering needs to run at database scale or join against road-geometry data** (which PROJECT.md explicitly defers to a later version). For v1 volume (crowdsourced reports, not firehose telemetry), scikit-learn in Python is simpler to reason about, easier to log/debug/version, and keeps clustering logic in the same language as the rest of the intelligence layer (evidence fusion, health scoring) rather than splitting business logic between SQL and Python. |

### Mapping (Frontend)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Leaflet | latest stable 1.9.4 | Core mapping library | Locked by PROJECT.md. **Do not adopt Leaflet 2.0** — it is alpha-only as of research date, with breaking API changes (constructors replace factory methods, global `L` object removed, pointer events replace mouse/touch events). Stay on the 1.9.x line for any 2026 production build. |
| react-leaflet | latest 5.0.0 | React bindings for Leaflet | Requires **React 19** as a peer dependency (locks in the React version choice above). `LeafletProvider` was removed from the core package in this version — check the v5 migration notes if porting any existing v3/v4 code/examples. |
| react-leaflet-cluster (or leaflet.markercluster via a wrapper) | latest | Marker clustering on the public map | Needed once report/detection density makes individual markers unreadable at low zoom — pairs naturally with the DBSCAN-derived clusters, but is a separate *rendering* concern from the backend clustering pipeline. |

### Time-Series Trend Forecasting (Health Score)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| statsmodels | latest 0.15.0 | `ExponentialSmoothing` (Holt's linear/double exponential smoothing) | **Primary recommendation** for the 30/60/90-day health-score forecast baseline once a segment has ≥4–5 historical health-score observations. `statsmodels.tsa.holtwinters.ExponentialSmoothing(series, trend='add', damped_trend=True)` gives a damped linear trend — damping is important here because an undamped linear extrapolation can predict health scores below 0 or above 100 over a 90-day horizon, which a damped trend resists. Fully transparent (α/β smoothing params are inspectable), no black-box, satisfies PROJECT.md's "no deep learning until data exists" constraint directly. |
| numpy / scipy (`numpy.polyfit` or `scipy.stats.linregress`) | current (ships with any modern Python env) | Simple OLS linear-trend fallback for very sparse series (2–3 points) | Holt's method needs a handful of points to be meaningful; for a brand-new segment with only 2–3 RoadObservation entries, plain linear regression on (time, health_score) is simpler, has a well-understood confidence interval, and is just as explainable. **Recommended pattern: method escalation** — use linear regression below a data-point threshold (e.g. <5 observations), switch to damped Holt exponential smoothing above it. Both must ship with an explicit, human-readable explanation of the forecast method used per PROJECT.md's explainability requirement. |
| ~~Prophet~~ | — | — | **Explicitly out of scope** — see "What NOT to Use" below. |

### ML Inference Serving (in FastAPI)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| ultralytics native (`YOLO(weights_path)`) loaded once at app startup | — | Primary inference path | For a citizen-reporting app's request volume (well under 10 req/s at v1 scale), plain FastAPI + a YOLO model instance loaded once in a startup event/lifespan hook — **not per-request** — is the recommended pattern. Load into a module-level singleton; guard concurrent access if running multi-threaded (Ultralytics docs recommend per-thread instantiation for true thread-safety, or simpler: run inference calls through a single worker/queue to avoid concurrent-access issues on one model instance). |
| ONNX export + onnxruntime (latest 1.30.0) | optional, later | CPU-optimized inference path | Not needed for v1, but note the upgrade path: export the trained RDD2022 YOLOv8 weights to ONNX (`model.export(format='onnx')`) and swap to `onnxruntime.InferenceSession` if/when CPU inference latency becomes a bottleneck — ONNX Runtime is meaningfully faster and lighter on CPU than native PyTorch inference. Keep both `.pt` (dev/testing, easy to re-export/retrain) and `.onnx` (deploy) artifacts once you do this. |
| ~~TorchServe~~ / ~~Triton~~ | — | — | **Explicitly out of scope for v1** — see "What NOT to Use" below. |

### Background Job Handling for ML Inference

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| arq | latest 0.28.0 (Redis-backed) | Async job queue for YOLO inference | **Recommended**: run YOLO detection as a background job, not inline in the upload request/response cycle. A citizen uploads an image → the API immediately returns "report received, processing" → an `arq` worker picks up the job, runs YOLO inference, persists Detection rows, triggers downstream clustering/evidence-fusion. `arq` is asyncio-native (matches FastAPI's async style, no sync/async bridging), lightweight (just Redis, not a broker like RabbitMQ), and has built-in retry/cron support — appropriately sized for an early-stage project, with a clear upgrade path to Celery if task variety/scale grows later. |
| Redis | latest 8.x server (self-hosted or managed) | arq broker/result backend | Required dependency for `arq`. Also reusable later for caching (e.g. cached map tile queries, cached health-score aggregates). |
| ~~FastAPI `BackgroundTasks`~~ | — | — | **Explicitly out of scope for the inference path** — see "What NOT to Use" below. Fine only for truly trivial fire-and-forget work (e.g. sending a confirmation notification), never for the core detection pipeline. |
| ~~Celery~~ | — | — | Not recommended at v1 — see "What NOT to Use" / Alternatives below. |

### Image Storage

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| MinIO | latest server + `minio` Python SDK 7.2.20 (S3-compatible) | Object storage for uploaded report images | **Recommended over raw local-disk writes even at this early stage.** MinIO is self-hosted, free, and speaks the real S3 API (via `boto3` or the `minio` SDK) — meaning the exact same client code works against MinIO in dev/self-hosted deployment and against AWS S3 / Cloudflare R2 in a later production deployment; you only swap the endpoint URL and credentials, never application code. Local-disk storage (`UPLOAD_DIR/`) is the "cheaper to start" option and is acceptable for a throwaway prototype, but for RoadTwin — where images are permanent evidence tied to a longitudinal RoadObservation history that must remain retrievable for the life of the project — object storage semantics (content-addressed keys, presigned URL access, straightforward backup/replication) pay for themselves almost immediately. Use MinIO via Docker Compose alongside Postgres/Redis from day one. |
| Presigned URLs (short-lived) | — | Secure image access pattern | Never expose permanent public URLs to uploaded images; generate short-lived presigned GET URLs per dashboard/map request instead, so access can later be gated by auth/role without a storage migration. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | latest 0.0.32 | Multipart form parsing | Required by FastAPI for any `UploadFile` (image upload) endpoint. |
| Pillow / exifread | latest | EXIF GPS extraction | To auto-populate geolocation from an uploaded photo's EXIF metadata when the citizen doesn't manually drop a pin (PROJECT.md: "auto or manual pin"). |
| pydantic-settings | latest (2.x) | Environment/config management | Standard companion to Pydantic v2 for typed `.env`-driven settings (DB URL, MinIO/Redis endpoints, model weights path). |
| httpx | latest | Async HTTP client | For any outbound calls (e.g. future traffic/weather enhancement inputs, PROJECT.md explicitly defers these but the client choice is worth fixing now: `httpx` is the async-native standard, replacing `requests` in async codebases). |
| pytest + pytest-asyncio | latest | Testing | Standard Python test stack; needed given the locked build order (schema → detections → clustering → …) benefits heavily from unit tests gating each stage before the next is built on top. |
| React Query (TanStack Query) | latest 5.x | Frontend server-state management | Recommended (not mandated) for the authority dashboard's data fetching (network overview, priority queue, road detail) — avoids hand-rolled loading/error/cache state for what will be a data-heavy dashboard. |
| Zustand or React Context | latest | Frontend local/UI state | Lightweight alternative to Redux for map filters, selected-segment state, etc. — Redux is unnecessary overhead for this app's state shape. |

## Installation

# --- Backend (Python) ---

# --- Frontend (npm) ---

# --- Infra (docker-compose services) ---

# postgres (with postgis image, e.g. postgis/postgis:16-3.4), redis, minio

## Alternatives Considered

| Category | Recommended | Alternative | Why Not (for v1) |
|----------|-------------|-------------|-------------------|
| Spatial clustering | scikit-learn DBSCAN (Python) | PostGIS `ST_ClusterDBSCAN` (SQL) | Same algorithm; PostGIS wins once clustering must run at DB scale or join road geometry — both deferred concerns per PROJECT.md. Keep clustering in Python for now so it lives next to the rest of the intelligence layer and is easy to unit test/version independently of the schema. |
| Inference serving | ultralytics native in-process (FastAPI) | ONNX Runtime | ONNX is a straight performance upgrade path, not a different architecture — adopt when CPU latency actually becomes a bottleneck, not preemptively. |
| Inference serving | ultralytics native / ONNX | TorchServe / Triton | Both are built for high-QPS or multi-model GPU-batched serving; RoadTwin's v1 traffic (crowdsourced report volume) doesn't approach the threshold (>1000 req/s) where TorchServe's managed batching outperforms a simple FastAPI wrapper. Re-evaluate only if inference becomes the throughput bottleneck at scale. |
| Job queue | arq (Redis) | Celery (Redis/RabbitMQ) | Celery is the safer choice once you have 10+ distinct task types, need broker failover, or run multi-worker fleets on Kubernetes — none of which apply at v1. arq's async-native design also avoids the sync/async bridging overhead Celery requires inside a FastAPI app. Migrating from arq to Celery later is a contained, well-trodden path if job diversity grows. |
| Image storage | MinIO (S3-compatible) | Local disk (`UPLOAD_DIR/`) | Local disk is the "even cheaper to start" option and is fine for a pure throwaway prototype with no persistence guarantees. RoadTwin's images are longitudinal evidence, not disposable — object-storage semantics (presigned access, easy backup, zero-code-change path to real S3/R2) are worth the one extra Docker Compose service from day one. |
| Forecasting | statsmodels Holt exponential smoothing (+ linear regression fallback) | Prophet, ARIMA, LSTM/deep learning | See "What NOT to Use" — explicitly excluded by PROJECT.md's constraints. |
| Database | PostgreSQL (+ PostGIS from day one) | SQLite | SQLite is explicitly "acceptable for dev" per PROJECT.md constraints but lacks PostGIS; use it only for fast local iteration/tests, not as the target production database, to avoid a late spatial-query migration. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Prophet (or any Facebook/Meta-style decomposable forecasting model) | Black-box relative to its stated "interpretable components," heavier dependency footprint (Stan backend), and explicitly the kind of premature-complexity forecasting tool PROJECT.md rules out before longitudinal data exists to validate against. Also poorly suited to genuinely sparse per-segment series (it's designed for longer daily/weekly series with seasonality, which RoadSegment health-score history won't have for a long time). | statsmodels `ExponentialSmoothing` (Holt damped trend) once ≥4-5 points exist; plain OLS linear regression before that. |
| Any deep-learning forecasting model (LSTM, Transformer-based time-series, etc.) | PROJECT.md explicitly places this Out of Scope: "do not build until a longitudinal RoadObservation dataset actually exists to train/validate against." | Transparent trend-based baseline (above), revisit only after real longitudinal data accumulates. |
| FastAPI `BackgroundTasks` for YOLO inference | In-process, no persistence — a server restart silently drops in-flight inference jobs; no retry semantics; blocks the same worker process handling other requests. Fine for trivial fire-and-forget notifications only. | `arq` (Redis-backed async job queue). |
| TorchServe / NVIDIA Triton for v1 | Both are designed for high-throughput or multi-model GPU-batched serving scenarios; at RoadTwin's v1 traffic level they add substantial operational complexity (separate serving process, model archiving/config, additional infra to run and monitor) with no throughput benefit yet. | Plain FastAPI + ultralytics native inference (upgrade to ONNX Runtime first if CPU latency becomes the bottleneck, long before TorchServe/Triton are justified). |
| Leaflet 2.0 (alpha) | Breaking API changes (constructors replace factory methods, global `L` removed, new pointer-event model) and not yet stable as of this research; building against an alpha risks a painful mid-project upgrade or being stuck pinned to a moving alpha. | Leaflet 1.9.x (stable) + react-leaflet 5.x. |
| Storing uploaded images directly as DB blobs (bytea columns) | Bloats the primary datastore, slows backups/replication, and makes CDN/presigned-URL-based serving impossible without extra plumbing. | MinIO/S3-compatible object storage with a `storage_key` column in Postgres referencing the object. |
| Synchronous/blocking YOLO inference inside the upload request handler | Blocks the FastAPI event loop or ties up a worker thread for the full inference duration (hundreds of ms to seconds), directly hurting upload endpoint responsiveness and throughput under any real report volume. | Background job via `arq`; return "processing" status immediately, update Report/Detection status asynchronously. |
| Celery as the default choice at v1 | More moving parts (broker choice, worker supervision, heavier config surface) than the problem currently needs; appropriate once task diversity and team/infra scale grow, not before. | `arq` now; migrate to Celery later if/when justified by scale. |

## Stack Patterns by Variant

- Use PyTorch CUDA build + optionally TensorRT export for the YOLOv8 model
- Because GPU inference throughput benefits are substantial for object detection workloads, and TensorRT specifically optimizes GPU memory/latency beyond plain PyTorch-on-GPU
- Use PyTorch CPU build initially; migrate the exported model to ONNX + onnxruntime if inference latency becomes a bottleneck
- Because RDD2022-tuned YOLOv8n/s models are small enough to run acceptably on CPU for report-driven (not live-video) inference volume
- Reconsider PostGIS `ST_ClusterDBSCAN` over in-Python scikit-learn DBSCAN, and Celery over arq
- Because both scikit-learn-in-Python and arq-on-Redis are the right *starting* choices but have known scaling ceilings that PostGIS-in-SQL and Celery's broker-backed architecture are built to exceed
- Only then evaluate a learned forecasting model (and even so, prefer simple/interpretable ML — e.g. gradient-boosted trees on engineered features — over deep learning, consistent with PROJECT.md's explainability requirement for every priority score)
- Because PROJECT.md is explicit that deep-learning forecasting is premature complexity until real data exists to validate against

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| fastapi>=0.115 | pydantic>=2.7,<3 | FastAPI 0.14x series requires Pydantic v2; do not mix with pydantic v1 models except via FastAPI's temporary `pydantic.v1` compatibility shim (avoid relying on this long-term). |
| react-leaflet@5.0.0 | react@19.x | react-leaflet 5 declares React 19 as a peer dependency — pin React to 19.x across the frontend, not just the map component. |
| sqlalchemy>=2.0 (async) | asyncpg (runtime), psycopg[binary] (Alembic sync migrations) | Use asyncpg for the app's async engine; Alembic's autogenerate/migration commands conventionally run in sync mode, so keep a sync driver (`psycopg`) available for the Alembic env, or configure Alembic's async template if you want a single driver. |
| geoalchemy2 | sqlalchemy>=2.0, PostGIS 3.x on the Postgres server | Requires the PostGIS extension actually enabled (`CREATE EXTENSION postgis;`) in the target database — this must be part of the initial migration/setup, not assumed. |
| ultralytics | torch>=1.8 (practically: use a current 2.x PyTorch build matching your Python version and CPU/CUDA target) | Pin the PyTorch build explicitly (CPU vs CUDA wheel) in requirements — `pip install ultralytics` alone will pull a default PyTorch build that may not match your deployment target. |
| arq | redis (server) — any recent Redis 6+/7+/8+ | No special version coupling; just needs a reachable Redis instance, which MinIO/Postgres can share a docker-compose network with. |

## Sources

- [ultralytics PyPI](https://pypi.org/project/ultralytics/) — verified current version (8.4.158) directly via PyPI JSON API — HIGH confidence
- [FastAPI PyPI / release notes](https://fastapi.tiangolo.com/release-notes/) — verified current version (0.141.1) — HIGH confidence
- [Pydantic GitHub releases](https://github.com/pydantic/pydantic/releases) / PyPI — verified current version (2.13.5) — HIGH confidence
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/) — verified current version (2.0.54) — HIGH confidence
- [GeoAlchemy2 PyPI](https://pypi.org/project/geoalchemy2/) — verified current version (0.20.0) — HIGH confidence
- [react-leaflet npm registry](https://www.npmjs.com/package/react-leaflet) — verified current version (5.0.0) directly via npm registry API — HIGH confidence
- [Leaflet GitHub — "Leaflet V2.0 Coming Soon" issue](https://github.com/PaulLeCam/react-leaflet/issues/1165) — verified Leaflet 2.0 alpha status — MEDIUM confidence (single-source, cross-checked against npm registry version 1.9.4 for stable)
- [statsmodels docs — Exponential Smoothing](https://www.statsmodels.org/stable/examples/notebooks/generated/exponential_smoothing.html) — verified current version (0.15.0) and Holt/ExponentialSmoothing API — HIGH confidence
- [Crunchy Data — PostGIS Clustering with DBSCAN](https://www.crunchydata.com/blog/postgis-clustering-with-dbscan) / [scikit-learn DBSCAN docs](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html) — cross-checked comparison — MEDIUM confidence
- [Deployment Decision Framework: TorchServe vs FastAPI vs Triton](https://theneuralbase.com/torchserve/learn/advanced/decision-framework/) / [ultralytics/ultralytics#8235 — Best practice to wrap YOLOv8 with FastAPI](https://github.com/ultralytics/ultralytics/issues/8235) — cross-checked across multiple articles — MEDIUM confidence
- [FastAPI Background Tasks: Celery vs ARQ vs RQ](https://medium.com/@rameshkannanyt0078/fastapi-background-tasks-celery-vs-arq-vs-rq-2026-benchmarks-decision-guide-f99598aa21eb) / [arq PyPI](https://pypi.org/project/arq/) — verified arq version (0.28.0) + cross-checked decision framework across multiple articles — MEDIUM-HIGH confidence
- [FastAPI MinIO Integration](https://medium.com/@mojimich2015/fastapi-minio-integration-31b35076afcb) / [MinIO GitHub](https://github.com/minio/minio) / minio PyPI (verified version 7.2.20) — MEDIUM confidence
- [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) — official FastAPI project reference stack — MEDIUM confidence (single canonical source, widely cited)
- npm registry API (react, leaflet, vite direct version lookups) — HIGH confidence (primary registry source)

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
