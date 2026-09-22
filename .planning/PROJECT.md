# RoadTwin

## What This Is

RoadTwin is a predictive road-health and maintenance-intelligence system. Citizens submit geotagged photos of road damage; a YOLOv8/RDD2022 perception layer detects the damage, and RoadTwin fuses those observations over time into per-road-segment health profiles — tracking condition, deterioration rate, and future risk — to produce an explainable, ranked maintenance queue for road authorities.

## Core Value

YOLO detects what is visible; RoadTwin determines what the road's condition means, how it is changing, what may happen next, and what should be fixed first. The road segment — not the individual report — is the primary intelligence entity.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Citizens can submit a report: image + GPS (auto or manual pin) + timestamp + optional description
- [ ] Every YOLOv8/RDD2022 detection in an image is persisted individually (type, confidence, bbox, severity) — not just one report-level result
- [ ] Observation-level severity is computed from bounding-box features (area, damage type)
- [ ] Duplicate/near-duplicate citizen reports are merged via GPS spatial clustering (DBSCAN starting point)
- [ ] Point observations are aggregated into road segments (road-network-aware segmentation deferred until geometry is available)
- [ ] Community upvotes and verification contribute to an evidence score per observation
- [ ] Evidence score combines ML confidence, observation count, spatial agreement, temporal consistency, and community validation — YOLO confidence is never treated as real-world certainty alone
- [ ] Every road segment has a longitudinal RoadObservation history (multiple observations over time, not a single snapshot)
- [ ] Road Health Score (0-100) is computed per segment from severity burden, damage density, temporal deterioration, and evidence burden, with published interpretation bands (Excellent/Good/Poor/Critical/Severely degraded)
- [ ] Deterioration rate is computed from health-score history: (HealthScore_t2 − HealthScore_t1) / elapsed_time
- [ ] A transparent, non-deep-learning trend-based baseline forecasts health score at 30/60/90-day horizons per segment
- [ ] Maintenance priority score ranks road segments using severity, deterioration rate, damage density, evidence confidence, traffic exposure, road importance, vulnerable-location proximity, and repair recency
- [ ] Every priority score has a human-readable explanation (why this road ranked where it did)
- [ ] Public map shows road health, damage clusters, reports, and trends
- [ ] Authority dashboard shows network overview, road health map, ranked priority queue, road detail (history/composition/evidence/forecast), and per-road explainability
- [ ] Admin/repair workflow: report status transitions and repair tracking (retained from MVP baseline)
- [ ] Data model implements Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction, and MaintenanceRecommendation as distinct, related entities

### Out of Scope

- Deep-learning forecasting model — do not build until a longitudinal RoadObservation dataset actually exists to train/validate against; start with a transparent trend baseline
- Mandatory traffic / weather / road-classification / repair-history inputs — enhancement-only, added last, never a blocker for the first working system
- Replacing or retraining YOLO to "claim novelty" — YOLO/RDD2022 stays the perception baseline; the product's novelty is the intelligence layer above it
- Many disconnected AI features — every new capability must plug into the fusion → segment → health → prediction → priority pipeline, not bolt on separately
- Treating a raw citizen report as equivalent to a confirmed physical defect without evidence fusion
- Presenting the RHS/priority weights as scientifically validated — they are placeholders pending experimental tuning
- Road-network-aware (geometry-based) segmentation for v1 — GPS/DBSCAN clustering is the v1 approach; true road-network segmentation is deferred until reliable road geometry data is available

## Context

This is a from-scratch build in this repository (confirmed empty, no prior git history) implementing a previously-designed architecture. The design explicitly retains an "MVP foundation" stack — React/Vite frontend, FastAPI backend, YOLOv8/RDD2022 detection, geolocation, crowdsourced reporting, Leaflet mapping, PostgreSQL/SQLite, community verification, and an admin repair workflow — as the base layer, with RoadTwin's evidence-fusion/segment/health/prediction/decision layers built on top of it from the start (not bolted on later).

A full architecture and data-model spec was authored ahead of this session (originally shared as `RoadTwin_Architecture_and_Input_Specification.pdf`; transcribed and committed to the repo at `.planning/reference/RoadTwin-Architecture-Input-Spec.md` since the PDF itself was never checked in) covering: end-to-end pipeline (citizen input → perception → evidence fusion → road segment engine → road health engine → predictive intelligence → maintenance decision engine → public map / authority dashboard), full data model for all 7 entities (§4), the Road Health Score formula and interpretation bands (§6), deterioration-rate formula (§7), evidence-fusion inputs (§9), spatial-clustering approach (§10, DBSCAN → road segments), maintenance priority-score inputs (§11), dashboard layout (§12), a locked implementation order (§16: schema → detections → clustering → observations → health score → deterioration → forecast baseline → priority → dashboard → external inputs last), and an explicit "what not to do" list (§17). **This document is the primary source of truth for scope, exact entity field lists, and sequencing — read it directly rather than relying on summaries; the roadmap mirrors its Implementation Order section closely.**

The user's own explanatory writeup (this session) restates and slightly extends this spec with worked examples, dashboard mockups, and a suggested backend module layout (`models/`, `services/{spatial,intelligence,maintenance}/`, `routes/`) — useful as implementation reference, not additional requirements.

## Constraints

- **Tech stack**: React/Vite frontend, FastAPI backend, PostgreSQL (SQLite acceptable for dev), Leaflet for maps, YOLOv8 + RDD2022 weights for perception — fixed by prior design, not open for re-litigation
- **Build order**: Schemas/data contracts must be locked before intelligence-layer code is written; perception and raw-detection persistence come before clustering; clustering before segments; segments before health scoring; health scoring before deterioration; deterioration before forecasting; forecasting before priority scoring; priority scoring before the authority dashboard is built around it — per the spec's Implementation Order
- **Forecasting approach**: v1 must use a transparent, explainable trend-estimation method — no deep-learning forecasting model until enough longitudinal RoadObservation data has been collected to justify it
- **External data**: Traffic, weather, road classification, repair history, and proximity-to-vulnerable-locations are enhancement inputs only — never required for the core pipeline to function

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Road segment (not report) is the primary intelligence entity | Individual reports are noisy point observations; the physical road is what authorities need to reason about and repair | — Pending |
| Persist every YOLO detection separately, not just a report-level summary | One image can contain multiple distinct defects; downstream health/evidence scoring needs per-defect granularity | — Pending |
| DBSCAN for spatial clustering (duplicate detection + segment aggregation) as v1, road-network-aware segmentation deferred | Practical starting point without requiring road geometry data; upgrade path stays open | — Pending |
| Evidence score is a function of ML confidence + independent corroboration, not raw YOLO confidence alone | YOLO confidence is model certainty, not real-world certainty; conflating them overstates evidence for a single low-corroboration report | — Pending |
| Transparent trend-based forecasting baseline before any ML forecasting model | No longitudinal data exists yet to train/validate a complex model against; premature complexity would be unvalidatable | — Pending |
| Build a dedicated longitudinal "RoadTwin Dataset" (RoadID × Time × Damage) rather than relying on RDD2022 alone | RDD2022 is a single-image perception benchmark with no temporal/geospatial structure; the deterioration/prediction layer requires repeated observations tied to the same physical segment over time | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-22 after initialization*
