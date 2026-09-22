# Roadmap: RoadTwin

## Overview

RoadTwin is built as a strictly staged pipeline, in the order the architecture spec locks in: lock the seven-entity data model first, then bring citizen reports in safely (identity + rate limiting), then run perception asynchronously so every individual detection survives, then turn raw points into stable road segments, then fuse evidence and accumulate longitudinal observation history, then derive health/deterioration/forecast from that history, and finally rank segments into an explainable priority queue surfaced through a public map and an authenticated authority dashboard. Each phase produces something a person can observe working end-to-end before the next phase builds on it — nothing here is a horizontal layer that can't be independently verified.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Schema & Core Data Contracts** - Lock the seven-entity data model (append-only history, status lifecycles, GPS accuracy) before any intelligence code is written
- [ ] **Phase 2: Ingestion, Citizen Identity & Rate Limiting** - Citizens can safely submit geotagged photo reports, attributed and spam-protected
- [ ] **Phase 3: Async Perception Pipeline** - Every submitted image is run through YOLOv8/RDD2022 in the background, with every detection persisted individually
- [ ] **Phase 4: Spatial Clustering & Segment Identity** - Near-duplicate reports merge via DBSCAN into road segments with stable, reconciled identity
- [ ] **Phase 5: Evidence Fusion & Longitudinal Observations** - Every observation gets a multi-signal evidence score, and segments accumulate real history over time
- [ ] **Phase 6: Health Scoring, Deterioration & Forecast Baseline** - Segments get an explainable health score, deterioration rate, and transparent 30/60/90-day forecast, gated by data sufficiency
- [ ] **Phase 7: Priority Scoring, Explainability & Dashboards** - Segments are ranked into an explained priority queue, surfaced via a public map and an authenticated authority dashboard with repair workflow

## Phase Details

### Phase 1: Schema & Core Data Contracts
**Goal**: The data model exists as a locked, coherent foundation — all seven core entities persisted with append-only time-series semantics and status lifecycles, ready for every downstream phase to build on.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: SCHM-01, SCHM-02, SCHM-03, SCHM-04
**Success Criteria** (what must be TRUE):
  1. All seven entities (Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, MaintenanceRecommendation) exist as distinct, related persisted models.
  2. RoadObservation, RoadHealth, and Prediction records are append-only — each computation creates a new record rather than overwriting a prior one.
  3. Report and Detection records carry a status field that starts at "unverified" and can transition through defined lifecycle states (e.g. unverified → corroborated → evidence-confirmed).
  4. A Report's location is stored with a GPS accuracy/error-radius value alongside latitude/longitude, not a bare coordinate pair.
**Plans**: 5 plans (4 waves)
Plans:
- [ ] 01-01-PLAN.md — Stack boots: Postgres 16 + PostGIS 3.4 up, Report ORM/contract/repository defined, end-to-end skeleton test written RED
- [ ] 01-02-PLAN.md — Alembic wired and revision 0001 applied to the live database; FastAPI skeleton API takes the e2e test green
- [ ] 01-03-PLAN.md — React 19 + Vite frontend page creates and lists reports in a browser; README documents the full-stack run
- [ ] 01-04-PLAN.md — The six remaining entities, their relationships, the append-only repository split, and revision 0002
- [ ] 01-05-PLAN.md — Seven-entity chain seed, live schema-status panel and status-lifecycle transitions made observable

### Phase 2: Ingestion, Citizen Identity & Rate Limiting
**Goal**: Citizens can submit road-damage reports that are safely and durably captured, attributable to a lightweight identity, and protected from spam and evidence-score gaming.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: INGT-01, INGT-02, INGT-03, INGT-04
**Success Criteria** (what must be TRUE):
  1. A citizen can submit a report with an image, GPS location (auto-captured or manually pinned), timestamp, and optional description, and receive confirmation it was recorded.
  2. Each submission is attributed to a lightweight identity (device/session ID or email) without requiring full account creation.
  3. Repeated rapid submissions from the same identity/IP are throttled or rejected once a configured rate limit is exceeded.
  4. Uploaded images are retrievable from object storage via a reference stored on the Report record.
**Plans**: TBD

### Phase 3: Async Perception Pipeline
**Goal**: Every submitted image is automatically analyzed for road damage in the background, with every individual detection preserved for downstream intelligence — never a synchronous, request-blocking inference step.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: PERC-01, PERC-02, PERC-03
**Success Criteria** (what must be TRUE):
  1. After a report is submitted, YOLOv8/RDD2022 inference runs via a background job queue without blocking or delaying the submission response.
  2. Each distinct damage detection in an image is persisted as its own Detection record (type, confidence, bounding box, bbox-area ratio, severity) — an image with multiple defects yields multiple Detection rows.
  3. Each Detection's severity is derived from its bounding-box features (area, damage type), not copied directly from raw model confidence.
**Plans**: TBD

### Phase 4: Spatial Clustering & Segment Identity
**Goal**: Nearby reports of the same physical damage are recognized as one thing, and the road segments they belong to have stable, durable identity across repeated clustering runs.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: SPAT-01, SPAT-02, SPAT-03
**Success Criteria** (what must be TRUE):
  1. Two citizen reports submitted for the same physical damage location are merged/linked as near-duplicates via GPS spatial clustering (DBSCAN) rather than counted as unrelated observations.
  2. Point-level observations are aggregated into persistent RoadSegment records representing stretches of road, not just raw points.
  3. Re-running the clustering/segmentation job on updated data reconciles onto existing RoadSegment IDs rather than minting new segment identities for the same physical road.
**Plans**: TBD

### Phase 5: Evidence Fusion & Longitudinal Observations
**Goal**: Every observation carries a defensible evidence score fusing multiple independent signals, and each road segment accumulates a genuine longitudinal history of observations rather than a single snapshot.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: EVID-01, EVID-02, EVID-03, EVID-04, HLTH-01
**Success Criteria** (what must be TRUE):
  1. Every observation has an evidence score computed from ML confidence, observation count, spatial agreement, temporal consistency, and community validation — never from ML confidence alone.
  2. Evidence-score fusion weights are stored as configuration values, and each score's computation logs the per-component contribution.
  3. A citizen can upvote/corroborate an existing report, and the system prevents a single identity from contributing more than one corroboration to a given report.
  4. Each RoadSegment accumulates multiple RoadObservation records over time, viewable as a history rather than a single current state.
**Plans**: TBD

### Phase 6: Health Scoring, Deterioration & Forecast Baseline
**Goal**: Each road segment has a current, explainable health score, a computed deterioration trend, and a transparent forecast of where its health is headed — with numeric outputs withheld when there isn't enough data to trust them.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: HLTH-02, HLTH-03, HLTH-04, FCST-01, FCST-02, FCST-03
**Success Criteria** (what must be TRUE):
  1. Each RoadSegment has a Road Health Score (0-100) computed from severity burden, damage density, temporal deterioration, and evidence burden, displayed with its interpretation band (Excellent/Good/Poor/Critical/Severely degraded).
  2. Each RoadSegment's deterioration rate is computed from its health-score history as (HealthScore_t2 − HealthScore_t1) / elapsed_time.
  3. A segment with too few observations or too short a history shows "insufficient data" for both deterioration rate and forecast instead of a computed number, using the same minimum-data gate for each.
  4. A segment with sufficient history shows a 30/60/90-day health-score forecast produced by a transparent, non-deep-learning trend method.
  5. Forecast values are compared against later-observed actuals, and this accuracy record is retained and viewable for evaluating forecast quality over time.
**Plans**: TBD

### Phase 7: Priority Scoring, Explainability & Dashboards
**Goal**: Road segments are ranked into an explainable maintenance priority queue, and both the public and authority audiences can see the intelligence pipeline's output through purpose-built, access-controlled views.
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: PRIO-01, PRIO-02, PRIO-03, PMAP-01, PMAP-02, AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, RPWF-01, RPWF-02
**Success Criteria** (what must be TRUE):
  1. Every RoadSegment has a maintenance priority score computed from severity, deterioration rate, damage density, evidence confidence, traffic exposure, road importance, vulnerable-location proximity, and repair recency, each paired with a human-readable explanation of why it ranked where it did.
  2. Priority and health scores are visibly labeled in the UI as provisional/tunable, never presented as scientifically validated.
  3. A member of the public can view a read-only map showing road health, damage clusters, reports, and trends without logging in, served by an API surface separate from the authority dashboard's read/write API.
  4. Authority staff can log in with an authority-staff role, only that authenticated role can perform dashboard-modifying actions, and authenticated staff can view network overview, road health map, ranked priority queue, per-road detail (history/composition/evidence/forecast), and per-road priority explanation.
  5. Authority staff can transition a report/segment through repair-status states (received → in progress → resolved), and the reporting citizen receives an in-app notification when that status changes.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Schema & Core Data Contracts | 0/5 | Planned | - |
| 2. Ingestion, Citizen Identity & Rate Limiting | 0/TBD | Not started | - |
| 3. Async Perception Pipeline | 0/TBD | Not started | - |
| 4. Spatial Clustering & Segment Identity | 0/TBD | Not started | - |
| 5. Evidence Fusion & Longitudinal Observations | 0/TBD | Not started | - |
| 6. Health Scoring, Deterioration & Forecast Baseline | 0/TBD | Not started | - |
| 7. Priority Scoring, Explainability & Dashboards | 0/TBD | Not started | - |
