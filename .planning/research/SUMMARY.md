# Project Research Summary

**Project:** RoadTwin — crowdsourced road-damage detection & geospatial predictive-maintenance system
**Domain:** Civic-tech crowdsourced reporting + ML perception + predictive-maintenance intelligence (hybrid of 311/SeeClickFix, PMS tools like StreetSaver/Cartegraph, and AI road-scoring like RoadBotics)
**Researched:** 2026-09-22
**Confidence:** MEDIUM-HIGH

## Executive Summary

RoadTwin combines three well-understood but rarely-combined system types: crowdsourced civic reporting (ingestion + geo-dedup), ML inference serving (async YOLOv8 perception), and predictive-maintenance/pavement-management systems (aggregation → health score → forecast → priority). Each piece independently has a validated, standard shape — the innovation is fusing citizen-report evidence with per-detection AI output and a transparent, explainable multi-factor priority score, something none of the reference products (SeeClickFix, StreetSaver, RoadBotics) do together. The stack is largely already locked by PROJECT.md (React/Vite, FastAPI, PostgreSQL/PostGIS, Leaflet, YOLOv8+RDD2022, DBSCAN, transparent forecasting) — research fills gaps with specifics: SQLAlchemy 2.0 async + GeoAlchemy2 for the ORM layer, arq+Redis for background inference/clustering jobs (not inline, not Celery at this scale), MinIO for S3-compatible image storage, and statsmodels' damped Holt exponential smoothing (with linear-regression fallback for sparse data) for the forecast baseline.

The recommended approach is a strictly staged, mostly-async pipeline: synchronous ingestion (Report API) → async YOLO inference via a job queue → batched/triggered DBSCAN clustering → append-only RoadObservation/RoadHealth time-series → deterioration rate → forecast → priority score with mandatory explanation → two separate read/write API surfaces (public map vs. authority dashboard). This order matches PROJECT.md's locked build sequence and is independently validated by all three reference domains — no reordering is recommended, only implementation refinements (build async and the two-API-module split early, not late).

The key risks are not exotic — they are specific, well-documented failure modes in adjacent domains: (1) treating unverified crowdsourced reports as equal-weight fact (StreetBump's train-track problem), (2) GPS noise breaking both duplicate-merge and segment assignment, (3) DBSCAN cluster/segment identity instability silently corrupting the longitudinal history the entire health/forecast pipeline depends on, (4) computing deterioration/forecasts on sparse, irregular data without a minimum-evidence gate, and (5) an authority dashboard that oversells certainty and loses government-user trust. All five are addressable with schema-level and job-design decisions made *early* (status lifecycles, GPS accuracy capture, segment-ID reconciliation, minimum-observation gates, explanation-as-first-class-data) — critically, several of these (segment ID stability, evidence-score component logging) are far more expensive to retrofit than to build correctly from the start, so the roadmap should front-load them into the schema and clustering phases rather than deferring them as polish.

## Key Findings

### Recommended Stack

Core stack is fixed by PROJECT.md; research fills in specific versions and glue. Backend: FastAPI 0.115+/Pydantic v2, SQLAlchemy 2.0 async + asyncpg + GeoAlchemy2 + Alembic migrations over PostgreSQL/PostGIS. Perception: `ultralytics` (YOLOv8/RDD2022) loaded once at startup, run through an async job queue — never inline. Clustering: scikit-learn DBSCAN (haversine metric) in Python for v1; PostGIS `ST_ClusterDBSCAN` deferred until DB-scale or road-geometry needs arise. Forecasting: statsmodels damped Holt exponential smoothing once ≥4-5 observations exist, linear regression fallback below that — explicitly not Prophet or deep learning. Frontend: React 19 + Vite + TypeScript + Leaflet 1.9.x (not 2.0 alpha) + react-leaflet 5 + TanStack Query.

**Core technologies:**
- FastAPI + Pydantic v2 — async-native backend, natural home for locking the 7 core entity schemas
- SQLAlchemy 2.0 (async) + GeoAlchemy2 + PostGIS — typed spatial queries, avoids raw SQL for clustering/segment logic
- arq + Redis — async-native background job queue for YOLO inference and clustering passes (lighter than Celery at this scale)
- MinIO (S3-compatible) — object storage for citizen-uploaded images, code-identical path to real S3/R2 later
- statsmodels (Holt damped trend) — transparent, explainable forecasting baseline consistent with the "no deep learning yet" constraint

### Expected Features

RoadTwin's 16 Active requirements cover the core intelligence pipeline well, but research identified several **gaps that are effectively prerequisites**, not nice-to-haves, for the Active features to function safely: lightweight citizen identity, submission rate limiting, admin/staff authentication with roles, and minimal status-change notification. Without citizen identity, the evidence score (which counts "observation count" and "community validation") can be trivially gamed. Without admin auth, the authority dashboard — a government-facing product — has no access control, a non-starter for a real buyer.

**Must have (table stakes, elevated to P1):**
- Geotagged photo report submission, public map, status tracking, duplicate detection — already covered by Active reqs
- Lightweight citizen identity (device/session ID, not full accounts) — precondition for evidence-score integrity
- Submission rate limiting — prevents evidence-score gaming
- Admin/staff authentication + role separation — precondition for a credible authority dashboard
- Minimal in-app status-change notification — closes the citizen trust loop

**Should have (differentiators, already in PROJECT.md):**
- Per-detection persistence (bbox/type/confidence), not just per-report — genuinely rare in reference products
- Evidence fusion (ML confidence + spatial + temporal + community, not raw confidence) — the single most defensible differentiator
- Multi-factor priority score with mandatory human-readable explanation — most externally-validated differentiator; matches what government-dashboard research says road authorities actually expect

**Defer (v2+):**
- CSV export, flag-for-moderation queue, weight sensitivity/what-if view (v1.x, add after real usage)
- Budget-constrained optimization, true road-geometry segmentation, deep-learning forecasting (v2+, already correctly excluded)
- Explicitly avoid: gamification (conflicts with evidence-score integrity), true real-time streaming dashboard (over-engineering for a days/weeks-scale domain)

### Architecture Approach

A strictly staged pipeline where each stage writes to exactly one entity type, decoupled via the database (not RPC) and via async job queues at the two genuinely slow/bursty boundaries (inference, clustering). The public map and authority dashboard are lightweight CQRS: same underlying tables, two separate API modules enforcing the read-only vs. read-write boundary at the code level, not just via auth middleware.

**Major components:**
1. **Report API (sync)** — accepts citizen submission, persists Report, enqueues inference job, returns immediately
2. **Inference Worker (async, arq)** — runs YOLOv8/RDD2022, persists Detection rows per Report
3. **Evidence Fusion / Spatial Clustering (async, batched)** — DBSCAN dedup + evidence score computation; must reconcile against existing RoadSegment IDs, not re-mint identity each run
4. **Segment Aggregation → Intelligence Layer (async, chained)** — RoadObservation → RoadHealth → deterioration rate → forecast, each append-only and independently schedulable
5. **Priority/Decision Engine + two read APIs** — on-read computation initially, graduating to materialized rows at scale; Public Map API (read-only) vs. Authority Dashboard API (read/write) as separate modules from day one

### Critical Pitfalls

1. **Unverified reports treated as fact at ingestion** — give every Report/Detection a status lifecycle (unverified→corroborated→evidence-confirmed) and apply cheap ingestion-time filters (rate limiting, cooldowns, plausibility checks) before anything enters the fusion pipeline.
2. **GPS noise treated as exact position** — capture accuracy/error-radius metadata, use it as a per-point weight in clustering, and make DBSCAN epsilon configurable per road class rather than a single global constant.
3. **DBSCAN cluster/segment ID instability across re-runs** — build an explicit reconciliation layer mapping new clustering output onto existing persisted RoadSegment IDs; never re-mint segment identity per run. This is one of the highest-cost-to-retrofit pitfalls since deterioration/forecast depend on stable segment identity.
4. **Deterioration/forecast computed on sparse, irregular data as if it were a regular time series** — enforce a minimum-observation/minimum-timespan gate before showing a numeric trend; below it, show "insufficient data" explicitly.
5. **Authority dashboard overclaims certainty, undermining government trust** — pair every priority/health score with a human-readable "why" breakdown and visible data-sufficiency indicator; never imply the weights are scientifically validated.

## Implications for Roadmap

Based on research, suggested phase structure (matches PROJECT.md's locked order, with structural refinements from research folded in):

### Phase 1: Schema & Core Data Contracts
**Rationale:** All research agrees schema decisions here are the hardest to change later — RoadHealth/RoadObservation must be append-only time-series from day one (Anti-Pattern 4 in ARCHITECTURE.md), and status lifecycle / GPS accuracy fields must exist before any report is ingested (Pitfall 1, 2).
**Delivers:** 7 core entity models (Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation) as Pydantic + SQLAlchemy models, Alembic migration baseline, PostGIS enabled.
**Addresses:** Foundation for all Active requirements; also the point to add citizen-identity and status-lifecycle fields (FEATURES.md gaps).
**Avoids:** Pitfall 1 (no status lifecycle bolted on later), Pitfall 4 (append-only history), Pitfall 2 (GPS accuracy captured at the source).

### Phase 2: Ingestion + Citizen Identity + Rate Limiting
**Rationale:** FEATURES.md and PITFALLS.md both independently converge on this being a precondition, not a follow-up — evidence-score integrity and dashboard credibility both depend on it existing before real traffic.
**Delivers:** Report submission API, lightweight citizen identity (device/session ID), submission rate limiting, image storage (MinIO).
**Uses:** FastAPI + python-multipart + MinIO from STACK.md.
**Avoids:** Pitfall 1 (spam/garbage propagating downstream), Security Mistakes table (GPS spoofing, image-reuse).

### Phase 3: Async Perception Pipeline
**Rationale:** Detection persistence must exist and be durable before any downstream stage can consume it; the sync/async boundary (queue-based inference) should be built here, not retrofitted later.
**Delivers:** arq+Redis job queue, YOLOv8/RDD2022 inference worker, Detection persistence.
**Implements:** Architecture Pattern 1 (Async Job Queue for ML Inference).
**Avoids:** Anti-Pattern 1 (synchronous inference-in-request).

### Phase 4: Spatial Clustering & Segment Identity
**Rationale:** Highest-cost-to-retrofit pitfall in the whole system (segment ID instability) — build the reconciliation layer up front, not as a later fix, since deterioration and forecast both depend on stable identity.
**Delivers:** DBSCAN dedup + segment resolution as a background/scheduled job with explicit segment-ID reconciliation and audit logging of splits/merges.
**Implements:** Architecture Pattern 2 (Batched/Triggered Aggregation).
**Avoids:** Pitfall 3 (DBSCAN cluster/segment ID instability) — this phase carries the highest research flag.

### Phase 5: Evidence Fusion & Longitudinal Observations
**Rationale:** Evidence score must exist before RoadObservation history is meaningful; weights must be configuration (not constants) from this phase onward per Pitfall 7.
**Delivers:** Evidence score computation (ML confidence + spatial + temporal + community validation), RoadObservation append-only records, configurable/versioned weights with component-level logging.
**Avoids:** Pitfall 7 (weights guessed once, never revisited).

### Phase 6: Health Scoring, Deterioration, Forecast Baseline
**Rationale:** Same three-stage chain (index → trend → forecast) seen in both IoT predictive maintenance and PMS literature; each should be its own schedulable/chainable job.
**Delivers:** RoadHealth scoring, deterioration rate with minimum-observation gate, 30/60/90-day forecast (statsmodels Holt damped trend + linear-regression fallback) with forecast-vs-actual tracking built in from day one.
**Uses:** statsmodels from STACK.md.
**Avoids:** Pitfall 4 (sparse-data instability), Pitfall 5 (forecast shipped before validatable — build accuracy tracking alongside, not after).

### Phase 7: Priority Scoring, Explainability & Dashboards
**Rationale:** Establish the public-map vs. authority-dashboard API module split now (even though PROJECT.md's dashboard UI comes last structurally, research flags the read/write boundary as cheap to establish early and expensive to retrofit — ideally the module boundary is set up alongside Phase 1, but the full dashboard UI belongs here).
**Delivers:** Multi-factor priority score with mandatory human-readable explanation, Public Map API (read-only), Authority Dashboard API (read/write, admin auth + roles), status-change notifications.
**Addresses:** FEATURES.md's most-validated differentiator (explainable priority queue); admin auth gap.
**Avoids:** Pitfall 6 (dashboard overclaiming certainty), Anti-Pattern 3 (one generic CRUD API for both frontends).

### Phase Ordering Rationale

- Matches PROJECT.md's locked order exactly (schemas → detection → clustering → observations → health → deterioration → forecast → priority → dashboard → external inputs last); ARCHITECTURE.md independently validates this order against three adjacent mature domains and recommends no reordering.
- Citizen-identity/rate-limiting is pulled forward into Phase 2 (rather than left implicit) because FEATURES.md and PITFALLS.md both show it's a functional precondition, not a polish item, for the evidence score to mean what it claims.
- Segment-identity reconciliation is called out as its own phase-level concern (Phase 4) rather than folded silently into "clustering," because it's the single highest-cost-to-retrofit pitfall identified across all four research files.
- External inputs (traffic/weather/road-classification/repair-history) remain explicitly deferred past all phases above, consistent with PROJECT.md's Out of Scope and reaffirmed by both FEATURES.md and ARCHITECTURE.md.

### Research Flags

Needs deeper research during planning:
- **Phase 4 (Spatial Clustering & Segment Identity):** Segment-ID reconciliation logic (spatial-overlap/centroid-proximity matching across re-clustering runs) has no single off-the-shelf pattern — needs implementation-specific research during planning.
- **Phase 6 (Health/Deterioration/Forecast):** The minimum-observation-gate thresholds and the exact robust-trend method (weighted rolling regression vs. simple escalation) need concrete tuning decisions, not just the transparent-method choice already made.
- **Phase 7 (Dashboard/Explainability):** UX pattern for visible data-sufficiency badges and drill-down explanation UI has no single reference implementation among the products studied — worth a UI-focused research pass.

Standard patterns (skip research-phase):
- **Phase 1 (Schema):** Well-documented SQLAlchemy 2.0 + GeoAlchemy2 + Alembic patterns.
- **Phase 2 (Ingestion):** Standard FastAPI upload + rate-limiting patterns, well established.
- **Phase 3 (Async Perception):** arq + ultralytics integration is a documented, common pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Version numbers verified directly against PyPI/npm; architectural/pattern guidance cross-checked via web search |
| Features | MEDIUM | Cross-checked across 7 queries against named products (SeeClickFix, FixMyStreet, Cartegraph, StreetSaver, RoadBotics); no primary vendor docs, so depth is directional |
| Architecture | MEDIUM-HIGH | Patterns well-established in three adjacent mature domains, cross-checked independently; RoadTwin's specific composition is this researcher's synthesis |
| Pitfalls | MEDIUM | Web-search-corroborated across multiple domains (civic-tech, ML calibration, geospatial clustering, predictive-maintenance, structural-health-monitoring); no single "RoadTwin-shaped" post-mortem exists since it's a novel combination |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- No primary-source validation of feature research against actual vendor documentation (SeeClickFix/StreetSaver/RoadBotics) — treat FEATURES.md competitor comparisons as directional; validate specific claims if a government pilot partner references a specific competitor tool.
- Segment-ID reconciliation algorithm (Pitfall 3) has no established off-the-shelf library — this needs a dedicated design spike during Phase 4 planning, not just architectural guidance.
- Minimum-observation thresholds for deterioration/forecast gating (Pitfall 4/5) are qualitatively justified but have no specific numeric recommendation from research — needs an explicit decision during Phase 6 planning (e.g., "N=5 observations, T=14 days minimum").
- DBSCAN epsilon values per road class are flagged as necessary but not quantified — needs empirical tuning against real or synthetic GPS accuracy data, not resolvable from research alone.

## Sources

### Primary (HIGH confidence)
- PyPI/npm registry direct version lookups (ultralytics, FastAPI, Pydantic, SQLAlchemy, GeoAlchemy2, react-leaflet, statsmodels, arq, minio)
- PROJECT.md (RoadTwin, this repository) — primary source of truth for scope/sequencing

### Secondary (MEDIUM confidence)
- MIT Technology Review / ResearchGate — StreetBump crowdsourcing false-positive case study
- Crunchy Data / scikit-learn docs — PostGIS vs. scikit-learn DBSCAN comparison
- Microsoft Learn (Azure Architecture Center) — CQRS pattern reference
- Nature Scientific Reports (2024) — predictive-maintenance data-scarcity failure modes
- SpiderStrategies / CSM Tech / ScienceDirect — government-dashboard trust research
- SeeClickFix, FixMyStreet, StreetSaver, Cartegraph, RoadBotics vendor/press pages — competitor feature analysis

### Tertiary (LOW confidence)
- Single-source Leaflet 2.0 alpha-status GitHub issue — cross-checked against npm registry stable version, treated as MEDIUM overall
- HDBSCAN docs / SciELO adaptive-epsilon paper — DBSCAN variable-density limitation, applied by analogy to RoadTwin's GPS data, not RoadTwin-specific validation

---
*Research completed: 2026-09-22*
*Ready for roadmap: yes*
