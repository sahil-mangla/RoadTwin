# Architecture Research

**Domain:** Crowdsourced perception + evidence fusion + spatial aggregation + longitudinal scoring + forecasting (predictive road-maintenance intelligence)
**Researched:** 2026-09-22
**Confidence:** MEDIUM-HIGH (architecture patterns are well-established in three adjacent, mature domains — ML inference serving, predictive-maintenance IoT, and pavement management systems — cross-checked across independent sources; RoadTwin's specific composition of these patterns is novel, so the *shape* is HIGH confidence, the exact module boundaries below are this researcher's synthesis)

## Standard Architecture

RoadTwin sits at the intersection of three well-understood system types, each of which independently validates a piece of the pipeline:

1. **Crowdsourced civic reporting** (SeeClickFix, FixMyStreet, 311 systems) → validates the ingestion + geo-dedup pattern
2. **ML inference serving** (async job-queue pattern) → validates the perception-layer boundary
3. **Predictive-maintenance / IoT asset monitoring** → validates the aggregation → health → forecast → priority chain (this is RoadTwin's closest architectural cousin — road segment = "asset", detections = "sensor events")
4. **Pavement Management Systems (PMS)** → validates that segment-first aggregation with a distinct condition-index stage is the domain-standard shape, not a RoadTwin invention

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│  INGESTION (sync, request/response)                                       │
│  ┌────────────────────┐                                                   │
│  │ Report API          │  POST image + GPS + timestamp + description      │
│  │ (FastAPI route)      │  → writes Report row, stores image, returns 201 │
│  └──────────┬──────────┘                                                  │
├─────────────┼───────────────────────────────────────────────────────────┤
│             ▼                        PERCEPTION (async, queued)          │
│  ┌────────────────────┐                                                   │
│  │ Inference Worker     │  YOLOv8/RDD2022 on queued image                 │
│  │ (Celery/RQ task)     │  → persists 1..N Detection rows per Report      │
│  └──────────┬──────────┘                                                  │
├─────────────┼───────────────────────────────────────────────────────────┤
│             ▼                EVIDENCE FUSION (async, triggered/batched)  │
│  ┌────────────────────┐                                                   │
│  │ Spatial Clustering   │  DBSCAN over GPS + time window                  │
│  │ / Dedup Service       │  → assigns Report/Detection to a cluster,      │
│  │                       │     computes evidence score                    │
│  └──────────┬──────────┘                                                  │
├─────────────┼───────────────────────────────────────────────────────────┤
│             ▼           SEGMENT & OBSERVATION LAYER (async, batched)     │
│  ┌────────────────────┐                                                   │
│  │ Segment Aggregation   │  Maps cluster → persistent RoadSegment          │
│  │ Service               │  (create-or-attach); writes RoadObservation    │
│  └──────────┬──────────┘  (one row per aggregation event, longitudinal)  │
├─────────────┼───────────────────────────────────────────────────────────┤
│             ▼           INTELLIGENCE LAYER (async, scheduled)            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐ │
│  │ Health Scoring       │→│ Deterioration Rate   │→│ Forecast Baseline   │ │
│  │ (RoadHealth)          │  │ (trend on history)   │  │ (Prediction)        │ │
│  └────────────────────┘  └────────────────────┘  └──────────┬─────────┘ │
│                                                                │           │
│                                          ┌─────────────────────┘           │
│                                          ▼                                 │
│                              ┌────────────────────┐                       │
│                              │ Priority Scoring     │  → MaintenanceRec.   │
│                              │ (Decision Engine)      │  ranked queue     │
│                              └──────────┬───────────┘                     │
├─────────────────────────────────────────┼────────────────────────────────┤
│                        READ APIS (sync)  ▼                                │
│  ┌────────────────────────────┐   ┌────────────────────────────┐        │
│  │ Public Map API (read-only)   │   │ Authority Dashboard API      │        │
│  │ denormalized/cached segment  │   │ (read/write: status, repair, │        │
│  │ view                          │   │  overrides, verification)    │        │
│  └────────────────────────────┘   └────────────────────────────┘        │
├──────────────────────────────────────────────────────────────────────────┤
│  DATA STORE (PostgreSQL + PostGIS)                                        │
│  Report │ Detection │ RoadSegment │ RoadObservation │ RoadHealth │        │
│  Prediction │ MaintenanceRecommendation                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Report API | Accept citizen submission, validate, persist raw Report, enqueue inference job | FastAPI route, sync, returns 201 immediately (does not wait on ML) |
| Inference Worker | Run YOLOv8/RDD2022 on the image, persist every detection (bbox, type, confidence, computed severity) | Background worker (Celery/RQ/arq) pulling from a queue; GPU/CPU-bound, scaled independently of the API |
| Evidence Fusion / Dedup Service | Cluster near-duplicate Reports (GPS + time window, DBSCAN), compute evidence score from ML confidence + corroboration + community votes | Triggered on new-Detection event or run on a short interval (e.g. every N minutes / every M new reports) — not per-single-report-synchronous |
| Segment Aggregation Service | Resolve a cluster to an existing RoadSegment or create a new one; write a RoadObservation record capturing this point-in-time aggregation | Batch/scheduled job (can be same worker pass as clustering); idempotent create-or-attach logic |
| Health Scoring Engine | Compute RoadHealth (0-100) from severity burden, damage density, temporal deterioration, evidence burden — one row per segment per scoring run | Scheduled job (e.g. nightly, or triggered after N new observations on a segment) |
| Deterioration/Forecast Engine | Compute deterioration rate from RoadHealth history; produce 30/60/90-day trend-based Prediction | Scheduled job, runs after Health Scoring; pure function over historical RoadHealth rows, no ML training needed for v1 |
| Priority/Decision Engine | Combine severity, deterioration rate, damage density, evidence confidence, (optional) traffic/road-importance/vulnerable-proximity/repair-recency into MaintenanceRecommendation with explanation | Scheduled job or computed on-read for the dashboard, depending on volume — start on-read, move to scheduled if segment count grows |
| Public Map API | Serve read-only segment health/trend/report data to the citizen-facing map | Denormalized/cached read model over RoadSegment + RoadHealth + Prediction; no write endpoints |
| Authority Dashboard API | Serve full segment detail (history, composition, evidence, forecast, explanation) + accept status/repair-workflow writes | Operates on canonical entities directly; the only component with write access to MaintenanceRecommendation status and repair records |

## Recommended Project Structure

```
backend/
├── models/                     # SQLAlchemy models — the 7 core entities
│   ├── report.py                # Report
│   ├── detection.py             # Detection (FK -> Report)
│   ├── road_segment.py          # RoadSegment
│   ├── road_observation.py      # RoadObservation (FK -> RoadSegment)
│   ├── road_health.py           # RoadHealth (FK -> RoadSegment, time-series)
│   ├── prediction.py            # Prediction (FK -> RoadSegment)
│   └── maintenance_recommendation.py  # MaintenanceRecommendation
├── services/
│   ├── perception/              # YOLOv8/RDD2022 inference wrapper, severity-from-bbox
│   ├── spatial/                 # DBSCAN clustering, dedup, segment resolution
│   ├── intelligence/            # health scoring, deterioration rate, forecast baseline
│   └── maintenance/             # priority scoring, explanation generation
├── workers/                     # queue task definitions (inference, clustering/aggregation, scoring)
│   ├── inference_tasks.py
│   ├── aggregation_tasks.py
│   └── scoring_tasks.py
├── routes/
│   ├── reports.py               # POST report (sync ingestion)
│   ├── public_map.py            # GET-only, read model
│   └── authority.py             # full CRUD, dashboard, status transitions
└── db/                          # PostGIS-enabled Postgres, migrations
```

### Structure Rationale

- **models/ mirrors the 7 entities exactly** — this is deliberate: the data model *is* the pipeline. Each stage of the pipeline writes to exactly one entity type, which keeps the async job boundaries legible (a worker either writes Detections, or RoadObservations, or RoadHealth rows — never several at once).
- **services/ split by pipeline stage, not by technical layer** — `spatial/` and `intelligence/` map directly to distinct scheduled jobs, matching the predictive-maintenance-IoT convention of separating "aggregation" from "scoring" from "forecasting" as independently schedulable stages.
- **workers/ isolated from routes/** — makes the sync/async boundary a physical file-structure boundary, not just a runtime one; prevents accidental synchronous calls into slow ML/clustering code from a request handler.
- **routes/public_map.py vs routes/authority.py as separate modules** — enforces the read-only vs read-write boundary at the code level from day one, even before any dashboard exists to consume it.

## Architectural Patterns

### Pattern 1: Async Job Queue for ML Inference

**What:** The Report API never runs YOLO inline. It persists the Report row, stores/queues the image, and enqueues an inference job (Celery/RQ/arq). A worker pool consumes the queue, runs detection, and persists Detection rows. The client gets an immediate 201 with a "processing" status; the UI polls or refetches.
**When to use:** Always, for this project — inference is CPU/GPU-bound and unpredictable in latency; blocking the citizen-facing submit request on it would create a poor UX and coupling between API scaling and inference scaling.
**Trade-offs:** Adds infra (a queue + worker process) and eventual-consistency UX (report appears before detections do) — acceptable and expected in this domain (citizens already expect "your report is being reviewed").

**Example:**
```python
# routes/reports.py
@router.post("/reports")
async def submit_report(payload: ReportIn, db: Session = Depends(get_db)):
    report = create_report(db, payload)          # sync write
    enqueue_inference.delay(report.id)             # async fire-and-forget
    return {"id": report.id, "status": "processing"}
```

### Pattern 2: Batched/Triggered Aggregation, Not Per-Request Clustering

**What:** DBSCAN clustering (for both duplicate-detection and segment aggregation) runs as a background pass — either on a short interval or triggered after a batch of new Detections lands — never synchronously inside the report-submission request.
**When to use:** Any time clustering needs to consider a *neighborhood* of existing points, not just the one just submitted — re-running DBSCAN correctly means re-evaluating cluster membership for nearby existing points too, which is not a cheap single-row operation.
**Trade-offs:** Introduces a short delay between "report submitted" and "segment updated" (seconds to minutes, not real-time) — acceptable, matches how PMS and civic-reporting systems behave in practice; a segment's health score changing a few minutes after a report is not a UX problem for this domain.

**Example:**
```python
# workers/aggregation_tasks.py
@celery_app.task
def run_clustering_pass():
    points = fetch_unclustered_detections()
    clusters = dbscan_cluster(points, eps=..., min_samples=...)
    for cluster in clusters:
        segment = resolve_or_create_segment(cluster)
        write_road_observation(segment, cluster)
```

### Pattern 3: Read-Model Separation for Public Map vs Authority Dashboard (Lightweight CQRS)

**What:** The public map and authority dashboard read from the same underlying tables but through different API modules — the public API returns only a denormalized, safe, read-only projection (segment health, trend, aggregate report counts); the authority API returns full canonical detail and is the only place writes happen (status transitions, repair records, manual verification/overrides).
**When to use:** Whenever read and write shapes diverge and traffic is asymmetric — exactly this project's public-map-heavy-read vs authority-occasional-write pattern. This is a named canonical CQRS use case; RoadTwin does not need full event sourcing, just the lightweight version (shared DB, two API surfaces, no separate write DB).
**Trade-offs:** Slight duplication of query logic across the two API modules is worth it for the hard access-control boundary (a bug in `public_map.py` cannot accidentally expose a write endpoint) — do not merge them into one generic CRUD router.

## Data Flow

### Primary Pipeline Flow (the "spine")

```
Citizen submits Report (image + GPS + timestamp)
    │ [SYNC — API write]
    ▼
Report row persisted → image queued for inference
    │ [ASYNC — worker]
    ▼
Detection rows persisted (1..N per Report, with bbox/type/confidence/severity)
    │ [ASYNC — scheduled/triggered clustering pass]
    ▼
Evidence Fusion: dedup cluster assigned, evidence score computed
    (combines ML confidence + observation count + spatial agreement +
     temporal consistency + community verification)
    │ [ASYNC — same or chained pass]
    ▼
RoadSegment resolved (create-or-attach) → RoadObservation written
    (one longitudinal record: this segment, at this time, this evidence)
    │ [ASYNC — scheduled, e.g. nightly or on N-new-observations trigger]
    ▼
RoadHealth computed (0-100, from severity burden + density + temporal
    deterioration + evidence burden) → new RoadHealth row appended
    │ [ASYNC — chained after health scoring]
    ▼
Deterioration rate computed from RoadHealth history (Δscore / Δtime)
    │ [ASYNC — chained]
    ▼
Prediction written (30/60/90-day trend-based forecast, transparent method)
    │ [ASYNC — chained or on-read]
    ▼
MaintenanceRecommendation computed (priority score + explanation) —
    ranks segments using severity, deterioration rate, density, evidence
    confidence, + optional traffic/importance/vulnerable-proximity/recency
    │
    ├──► [SYNC READ] Public Map API  — health, clusters, reports, trends
    └──► [SYNC READ+WRITE] Authority Dashboard API — full detail,
          explainability, status transitions, repair tracking
```

### Key Data Flows

1. **Write path (citizen → segment):** Strictly one-directional and staged — a Report never writes directly to RoadHealth; it must pass through Detection → evidence fusion → RoadObservation first. This staging is what makes every score explainable and traceable back to source reports.
2. **Read path (segment → both frontends):** Both frontends read the *same* underlying entities (RoadSegment, RoadHealth, Prediction, MaintenanceRecommendation) but through different API projections with different access levels — public gets aggregate/anonymized, authority gets full detail + write access.
3. **Feedback loop (authority → evidence):** Authority verification/repair actions feed back into evidence score and RoadObservation history (a repaired segment should reset/lower its damage signal) — this is a write from the Authority Dashboard into the same entities the pipeline populates, so the write path must be idempotent-safe against a concurrent scheduled scoring pass (use versioned/timestamped rows, not in-place mutation, for RoadHealth/RoadObservation).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Pilot / single city (0–~5k reports) | Single FastAPI process + single worker process is fine; clustering/scoring jobs can run every few minutes on a simple cron/Celery-beat schedule; SQLite acceptable for dev, Postgres+PostGIS for anything shared |
| Growing (multiple cities, tens of thousands of reports) | Separate worker pool sizing for inference (GPU-bound, expensive) vs clustering/scoring (CPU-bound, cheap) — per the async-ML-serving convention of dedicated queues per workload type; move priority scoring from on-read to scheduled/materialized if dashboard query latency degrades |
| Large (metro-wide, continuous ingestion) | Partition clustering/aggregation jobs geographically (by city/region) so one region's backlog doesn't delay another's; consider incremental/windowed DBSCAN instead of full re-cluster passes; materialize the public map read model into a cache/CDN-friendly layer since public read traffic will vastly outweigh authority write traffic (the canonical CQRS-asymmetric-traffic case) |

### Scaling Priorities

1. **First bottleneck: inference worker throughput.** YOLO inference is the most expensive single step; it must be on its own queue/worker pool from day one (even at small scale) so a burst of citizen reports doesn't block anything else.
2. **Second bottleneck: full-table re-clustering.** Naive DBSCAN re-run over the entire report history on every pass gets slower as data grows; plan to window it (only re-cluster points near new/changed reports) once report volume makes full passes slow — not needed for v1, but the aggregation job should be written so this windowing can be added later without a redesign.

## Anti-Patterns

### Anti-Pattern 1: Synchronous Inference-in-Request

**What people do:** Call YOLO inline inside the `POST /reports` handler and block the HTTP response until detection completes.
**Why it's wrong:** Couples API latency/availability to ML inference latency; a slow or crashed inference step takes down report submission entirely; makes horizontal scaling of the API tier pointless since inference is the real bottleneck.
**Do this instead:** Persist the Report synchronously, enqueue inference, return immediately with a processing status (Pattern 1 above).

### Anti-Pattern 2: Clustering/Scoring Inside the Same Transaction as Ingestion

**What people do:** After persisting a Report/Detection, immediately re-run DBSCAN and recompute RoadHealth for the affected segment in the same request.
**Why it's wrong:** Clustering correctness requires considering nearby existing points, not just the new one — doing this per-request is both slow and semantically wrong (you'd need to re-touch other clusters' membership too, which a single-report request has no business doing).
**Do this instead:** Batch/scheduled or triggered background aggregation pass (Pattern 2 above); ingestion and intelligence are separate transactions, separate services, separate scaling units.

### Anti-Pattern 3: One Generic CRUD API for Both Frontends

**What people do:** Build a single `/segments` REST API with full CRUD and let both the public map and the authority dashboard hit it, gating writes with auth middleware alone.
**Why it's wrong:** Public-vs-authority is a first-class architectural boundary in this domain (data sensitivity, denormalization needs, caching strategy, traffic shape all differ) — auth-middleware-only separation is fragile and makes it easy to accidentally leak a write endpoint or an over-detailed read field to the public.
**Do this instead:** Two API modules (Pattern 3 above) from the start, even if they share underlying query/service code — the module boundary is cheap insurance now and expensive to retrofit later.

### Anti-Pattern 4: Treating RoadHealth/Prediction as Mutable Single Rows

**What people do:** Store one RoadHealth row per segment and overwrite it on each scoring run (UPDATE instead of INSERT).
**Why it's wrong:** Destroys the longitudinal history the entire deterioration-rate and forecasting layer depends on — deterioration rate is explicitly `(HealthScore_t2 - HealthScore_t1) / elapsed_time`, which requires multiple historical rows, not a single current value.
**Do this instead:** RoadHealth (and RoadObservation) are append-only, timestamped, time-series tables from the very first schema — this is non-negotiable given the spec's own formulas.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| YOLOv8/RDD2022 model | Loaded in-process inside the inference worker (not a separate microservice for v1) | Keep it swappable behind a thin `perception/` interface so a future model-serving upgrade (e.g. Triton/TorchServe) doesn't touch pipeline code |
| Traffic / weather / road-classification / repair-history APIs | Enhancement-only inputs, added last, consumed by the Priority/Decision Engine as optional weighted factors | Per PROJECT.md constraints — must be structured so their absence doesn't block core scoring (nullable/default-weighted fields, not required joins) |
| Map tiles / Leaflet basemap | Standard client-side integration, no backend coupling | Public map and authority dashboard both consume the same tile provider |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Report API ↔ Inference Worker | Message queue (Celery/RQ/arq + Redis or similar broker) | Fire-and-forget from the API side; worker writes Detection rows directly to the DB |
| Inference Worker ↔ Evidence Fusion/Clustering | DB-mediated (worker writes Detections; clustering job reads unclustered Detections on its own schedule) | No direct RPC — decoupled via the database as the integration point, which is the standard pattern for this kind of staged pipeline |
| Clustering/Aggregation ↔ Intelligence Layer (Health/Deterioration/Forecast) | DB-mediated, chained scheduled jobs | Health scoring job reads RoadObservation history; deterioration reads RoadHealth history; forecast reads deterioration output — each stage is a pure read-then-write step over the previous stage's table |
| Intelligence Layer ↔ Priority/Decision Engine | DB-mediated or in-process function call if scoring is on-read | Priority scoring can start as an on-read computation inside the Authority Dashboard API for v1 (fewer moving parts), and graduate to a scheduled job producing materialized MaintenanceRecommendation rows once segment volume makes on-read computation slow |
| Public Map API ↔ Authority Dashboard API | No direct communication — siblings, both read (and one also writes) the same core tables | Enforce the access-control boundary at the module/router level, not just via auth checks (Anti-Pattern 3) |

## Build Order — Validation of the Locked Implementation Order

PROJECT.md locks this order: **schemas → detection persistence → GPS clustering/segment association → longitudinal observation history → health score → deterioration rate → forecast baseline → priority scoring → dashboard → external inputs last.**

This order is validated against all three comparable-domain patterns researched above and is the correct order. Specific confirmations and refinements:

1. **Schemas first — confirmed, and reinforced.** Because RoadHealth/RoadObservation must be append-only time-series (Anti-Pattern 4), the schema decisions here are harder to change later than in a typical CRUD app. Lock the "append-only, timestamped" shape for RoadObservation, RoadHealth, and Prediction *in the schema phase itself*, not as a later migration — this is the single highest-leverage adjustment to make to the plan.
2. **Detection persistence before clustering — confirmed.** Matches the async-ML-serving pattern: perception output must exist and be durable before any downstream stage can consume it. Also confirms the sync/async boundary should be built here: implement the queue-based inference pattern (Pattern 1) at this step, not deferred — retrofitting sync-inline inference into async later is a bigger rewrite than building it async from the start.
3. **Clustering/segment association before observation history — confirmed**, and matches both the civic-reporting-dedup pattern and the PMS segment-first-aggregation pattern. One refinement: build the clustering/aggregation job as a **background/scheduled job from the start** (Pattern 2), not a synchronous call — this is implied but not explicit in PROJECT.md's ordering language and is worth stating explicitly in the roadmap phase for this step, since it's an easy place to accidentally build it synchronous "just to get it working" and then have to rework it.
4. **Observation history before health score — confirmed.** Matches predictive-maintenance IoT convention exactly (aggregate → score). No adjustment.
5. **Health score before deterioration rate before forecast baseline — confirmed.** This is the same three-stage chain (index → trend → forecast) seen in both IoT predictive maintenance and PMS literature. No adjustment — but note each of these three should be its own schedulable/chainable job (not one monolithic function) so that later work (e.g. re-tuning the health formula) doesn't require re-deriving deterioration/forecast logic too.
6. **Priority scoring before dashboard — confirmed**, with a suggested refinement: **build priority scoring as an on-read computation first**, not a scheduled materialization job, since the dashboard doesn't exist yet to consume a materialized table and segment volume in early phases will be small. Graduate to scheduled/materialized MaintenanceRecommendation rows only once real usage shows on-read is too slow (this is a build-order micro-optimization, not a disagreement with the locked order).
7. **Dashboard before external inputs — confirmed.** Matches the CQRS/read-model pattern: build the two read/write API surfaces (Pattern 3) around the *core* entities first; external enhancement inputs (traffic/weather/etc.) should be added as optional weighted factors into the already-working Priority Engine, never as blockers threaded earlier into the pipeline.
8. **One addition not explicit in the locked order: decide the public map vs authority dashboard API/module split at the same time schemas are locked (step 1), even though the dashboard UI itself is built last.** The read/write access boundary (Pattern 3, Anti-Pattern 3) is cheap to establish early as two router modules and expensive to retrofit after both consumers exist — this is a structural decision, not a UI-build-order decision, so it belongs earlier than "build the dashboard."

**Net assessment: the locked order is correct and matches how comparable domains (predictive-maintenance IoT, pavement management systems, civic-reporting dedup) are built. No reordering is recommended.** The refinements above are about *how* to build each locked step (async from the start for inference and clustering; on-read-then-materialize for priority scoring; establish the two-API-module boundary early even though the dashboard UI comes last) rather than *when*.

## Sources

- [Async inference requests — Celery For ML](https://theneuralbase.com/celery-for-ml/learn/beginner/async-inference-requests/) — MEDIUM confidence
- [Asynchronous pattern — Mercari ML System Design Patterns](https://mercari.github.io/ml-system-design-pattern/Serving-patterns/Asynchronous-pattern/design_en.html) — MEDIUM confidence
- [Operationalizing Document AI: Microservice Architecture for OCR/LLM Pipelines](https://arxiv.org/pdf/2605.18818) — MEDIUM confidence
- [Predictive Maintenance with IoT and AI: Implementation Guide — Oxmaint](https://oxmaint.com/blog/post/predictive-maintenance-iot-ai-implementation-guide) — MEDIUM confidence
- [End-to-End Architecture for Real-Time IoT Analytics and Predictive Maintenance](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12074242/) — MEDIUM confidence
- [Remaining Useful Life Prediction Method for Stochastic Degrading Devices](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11859782/) — MEDIUM confidence
- [PostGIS Clustering with DBSCAN — Crunchy Data Blog](https://www.crunchydata.com/blog/postgis-clustering-with-dbscan) — MEDIUM confidence
- [civicfix: AI-powered smart city infrastructure reporting](https://www.irjmets.com/upload_newfiles/irjmets80100105126/paper_file/irjmets80100105126.pdf) — MEDIUM confidence
- [CQRS Pattern — Azure Architecture Center, Microsoft Learn](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs) — MEDIUM-HIGH confidence (vendor architecture reference, cross-checked)
- [Patterns for CQRS Read Models — The Coding Interface](https://thecodinginterface.com/blog/cqrs-read-model-patterns/) — MEDIUM confidence
- [Aggregation of condition survey data in pavement management](https://www.tandfonline.com/doi/full/10.1080/15732479.2020.1730409) — MEDIUM confidence (peer-reviewed)
- [Pavement condition index — Wikipedia](https://en.wikipedia.org/wiki/Pavement_condition_index) — MEDIUM confidence
- [GIS, A Tool for Pavement Management](https://www.diva-portal.org/smash/get/diva2:1064849/FULLTEXT01.pdf) — MEDIUM confidence
- PROJECT.md (RoadTwin, this repository) — HIGH confidence (primary source of truth for scope/sequencing)

---
*Architecture research for: RoadTwin (predictive road-health & maintenance-intelligence system)*
*Researched: 2026-09-22*
