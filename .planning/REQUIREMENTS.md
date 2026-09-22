# Requirements: RoadTwin

**Defined:** 2026-09-22
**Core Value:** YOLO detects what is visible; RoadTwin determines what the road's condition means, how it is changing, what may happen next, and what should be fixed first — the road segment, not the individual report, is the primary intelligence entity.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Schema (SCHM)

- [x] **SCHM-01**: System persists Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, and MaintenanceRecommendation as distinct, related entities
- [ ] **SCHM-02**: RoadObservation, RoadHealth, and Prediction are append-only time-series records (never mutated in place), so deterioration/forecast can be computed from history
- [x] **SCHM-03**: Report and Detection carry a status lifecycle (e.g. unverified → corroborated → evidence-confirmed) rather than being treated as confirmed fact on arrival
- [x] **SCHM-04**: Report captures GPS accuracy/error-radius metadata alongside latitude/longitude, not just a bare coordinate pair

### Ingestion (INGT)

- [ ] **INGT-01**: Citizen can submit a report with image + GPS (auto-captured or manual pin) + timestamp + optional description
- [ ] **INGT-02**: Citizen submissions are attributed to a lightweight identity (device/session ID or email — full account system not required)
- [ ] **INGT-03**: Submission endpoint enforces rate limiting per identity/IP to prevent spam and evidence-score gaming
- [ ] **INGT-04**: Uploaded images are stored in object storage addressable by the Report record

### Perception (PERC)

- [ ] **PERC-01**: Every YOLOv8/RDD2022 detection in a submitted image is persisted individually (damage type, confidence, bounding box, bbox-area ratio, severity) — not collapsed into a single report-level result
- [ ] **PERC-02**: Observation-level severity is computed from bounding-box features (area, damage type)
- [ ] **PERC-03**: Inference runs asynchronously via a background job queue, never inline in the submission request

### Spatial Clustering & Segments (SPAT)

- [ ] **SPAT-01**: Near-duplicate citizen reports are merged via GPS spatial clustering (DBSCAN starting point)
- [ ] **SPAT-02**: Point observations are aggregated into persistent RoadSegment entities
- [ ] **SPAT-03**: RoadSegment identity is stable across repeated clustering runs — new clustering output reconciles onto existing segment IDs rather than re-minting identity each run

### Evidence Fusion (EVID)

- [ ] **EVID-01**: Every observation has an evidence score combining ML confidence, observation count, spatial agreement, temporal consistency, and community validation
- [ ] **EVID-02**: Evidence score treats YOLO confidence as one input among several, never as real-world certainty on its own
- [ ] **EVID-03**: Evidence-score fusion weights are configuration values with logged per-component contributions, not hard-coded constants
- [ ] **EVID-04**: Citizens can upvote/corroborate an existing report, and each unique identity can contribute at most once per report to the community-validation signal

### Road Health & Deterioration (HLTH)

- [ ] **HLTH-01**: Every RoadSegment has a longitudinal RoadObservation history (multiple observations over time, not a single snapshot)
- [ ] **HLTH-02**: Road Health Score (0-100) is computed per segment from severity burden, damage density, temporal deterioration, and evidence burden, with published interpretation bands (Excellent/Good/Poor/Critical/Severely degraded)
- [ ] **HLTH-03**: Deterioration rate is computed from health-score history: (HealthScore_t2 − HealthScore_t1) / elapsed_time
- [ ] **HLTH-04**: Deterioration rate is withheld (shown as "insufficient data") until a segment has a minimum number of observations spanning a minimum timespan, rather than computed from a single two-point delta

### Predictive Forecasting (FCST)

- [ ] **FCST-01**: A transparent, non-deep-learning trend-based method forecasts each segment's health score at 30/60/90-day horizons
- [ ] **FCST-02**: Forecasts are withheld until the segment's observation history meets the same minimum-data gate as deterioration rate
- [ ] **FCST-03**: Forecast accuracy is tracked against later-observed actuals, so forecasting quality can be evaluated over time

### Maintenance Priority (PRIO)

- [ ] **PRIO-01**: Maintenance priority score ranks road segments using severity, deterioration rate, damage density, evidence confidence, traffic exposure, road importance, vulnerable-location proximity, and repair recency
- [ ] **PRIO-02**: Every priority score has a human-readable explanation of why the segment ranked where it did
- [ ] **PRIO-03**: Priority/health scores are visibly labeled as provisional/tunable in the UI, never presented as scientifically validated

### Public Map (PMAP)

- [ ] **PMAP-01**: Public map shows road health, damage clusters, reports, and trends
- [ ] **PMAP-02**: Public map is served by a read-only API surface, separate from the authority dashboard's read/write API

### Authority Dashboard (AUTH)

- [ ] **AUTH-01**: Authority staff can authenticate and are assigned an "authority staff" role distinct from anonymous public access
- [ ] **AUTH-02**: Dashboard-modifying actions (status changes, repair workflow) require an authenticated authority-staff role
- [ ] **AUTH-03**: Authority dashboard shows network overview (overall health, critical roads, rapidly deteriorating roads, predicted failures)
- [ ] **AUTH-04**: Authority dashboard shows a road health map and a ranked priority queue
- [ ] **AUTH-05**: Authority dashboard shows per-road detail: health history, damage composition, evidence, and forecast
- [ ] **AUTH-06**: Authority dashboard shows the explanation for each road's priority score (explainability view)

### Admin / Repair Workflow (RPWF)

- [ ] **RPWF-01**: Authority staff can transition a report/segment through repair-status states (e.g. received → in progress → resolved)
- [ ] **RPWF-02**: Reporting citizen receives a minimal in-app notification when their report's status changes

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Trust & Moderation

- **MODR-01**: Staff can flag an individual report for moderation review (fake photo, offensive content) beyond automated evidence scoring

### Dashboard Enhancements

- **DASH-01**: Authority staff can export dashboard data (CSV) for council/grant reporting
- **DASH-02**: Authority staff can adjust priority-score weights in a "what-if" view and see the ranking shift live

### Notifications

- **NOTF-01**: Email/SMS notification channel for status changes, in addition to in-app

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Deep-learning forecasting model | No longitudinal dataset yet to train/validate against; build the transparent trend baseline first |
| Mandatory traffic / weather / road-classification / repair-history inputs | Enhancement-only; must never block the core pipeline from functioning |
| Replacing or retraining YOLO for novelty | YOLO/RDD2022 stays the fixed perception baseline; novelty is the intelligence layer above it |
| Road-network-geometry-aware segmentation | Requires road geometry data not yet available; GPS/DBSCAN clustering is the v1 approach |
| Budget-constrained maintenance optimization ("given $X, which repairs maximize network health") | Requires cost-per-repair data RoadTwin doesn't model yet; needs the core ranked queue validated first |
| Gamification (badges, leaderboards, points for reporting) | Incentivizes report volume over quality; directly conflicts with evidence-score integrity |
| True real-time/streaming dashboard (sub-minute refresh, websockets) | Road condition changes on a days/weeks cadence; periodic refresh is functionally equivalent and far simpler |
| Full citizen account system with profile/history | Not required for evidence-score integrity or rate limiting; lightweight identity is sufficient for v1 |
| Presenting RHS/priority weights as scientifically validated | Weights are placeholders pending experimental tuning; overclaiming risks credibility with technical government buyers |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCHM-01 | Phase 1 | Complete |
| SCHM-02 | Phase 1 | Pending |
| SCHM-03 | Phase 1 | Complete |
| SCHM-04 | Phase 1 | Complete |
| INGT-01 | Phase 2 | Pending |
| INGT-02 | Phase 2 | Pending |
| INGT-03 | Phase 2 | Pending |
| INGT-04 | Phase 2 | Pending |
| PERC-01 | Phase 3 | Pending |
| PERC-02 | Phase 3 | Pending |
| PERC-03 | Phase 3 | Pending |
| SPAT-01 | Phase 4 | Pending |
| SPAT-02 | Phase 4 | Pending |
| SPAT-03 | Phase 4 | Pending |
| EVID-01 | Phase 5 | Pending |
| EVID-02 | Phase 5 | Pending |
| EVID-03 | Phase 5 | Pending |
| EVID-04 | Phase 5 | Pending |
| HLTH-01 | Phase 5 | Pending |
| HLTH-02 | Phase 6 | Pending |
| HLTH-03 | Phase 6 | Pending |
| HLTH-04 | Phase 6 | Pending |
| FCST-01 | Phase 6 | Pending |
| FCST-02 | Phase 6 | Pending |
| FCST-03 | Phase 6 | Pending |
| PRIO-01 | Phase 7 | Pending |
| PRIO-02 | Phase 7 | Pending |
| PRIO-03 | Phase 7 | Pending |
| PMAP-01 | Phase 7 | Pending |
| PMAP-02 | Phase 7 | Pending |
| AUTH-01 | Phase 7 | Pending |
| AUTH-02 | Phase 7 | Pending |
| AUTH-03 | Phase 7 | Pending |
| AUTH-04 | Phase 7 | Pending |
| AUTH-05 | Phase 7 | Pending |
| AUTH-06 | Phase 7 | Pending |
| RPWF-01 | Phase 7 | Pending |
| RPWF-02 | Phase 7 | Pending |

**Coverage:**

- v1 requirements: 38 total
- Mapped to phases: 38 (confirmed by roadmapper)
- Unmapped: 0

---
*Requirements defined: 2026-09-22*
*Last updated: 2026-09-22 after roadmap creation (HLTH-01 reassigned Phase 6 -> Phase 5: it belongs with the RoadObservation history created during evidence fusion, not the health-score computation that consumes it)*
