# RoadTwin — Architecture & Input Specification

> Transcribed verbatim from `RoadTwin_Architecture_and_Input_Specification.pdf` (the source document provided at project kickoff). This file is the persisted, in-repo copy of that spec — the PDF itself was never committed to the repository, only shared as a conversation attachment, which left `PROJECT.md`'s "primary source of truth" reference dangling. This file resolves that: it is now the canonical, git-tracked source for the data model and formulas referenced throughout `.planning/`.

**Core proposition:** Convert individual road-damage observations into continuously evolving road-segment health profiles that detect deterioration, predict future risk, and prioritize maintenance.

## 1. Strategic Direction

The original system is retained as the MVP foundation: React/Vite frontend, FastAPI backend, YOLOv8/RDD2022 road-damage detection, geolocation, crowdsourced reporting, Leaflet mapping, PostgreSQL/SQLite, community verification and an administrative repair workflow.

The major architectural shift is that YOLO becomes the perception layer, not the product itself. RoadTwin adds evidence fusion, road-segment modeling, health scoring, deterioration analysis, prediction and maintenance decision support.

## 2. End-to-End Architecture

```
CITIZEN INPUT
  Image + GPS + Timestamp + Optional description
        |
        v
PERCEPTION LAYER
  Existing YOLOv8 + RDD2022
  Damage type + confidence + bounding boxes
        |
        v
EVIDENCE FUSION
  Spatial clustering + duplicate detection
  Community verification + temporal matching
        |
        v
ROAD SEGMENT ENGINE
  Point observations -> road segments
  Damage density + composition + observation history
        |
        v
ROAD HEALTH ENGINE
  Road Health Score + severity burden
  Deterioration rate + verification/evidence score
        |
        v
PREDICTIVE INTELLIGENCE
  Deterioration forecasting + future risk
        |
        v
MAINTENANCE DECISION ENGINE
  Priority score + urgency + recommended action
  Optional budget / what-if optimization
        |
   +----+------------------+
   |                        |
   v                        v
PUBLIC MAP              AUTHORITY DASHBOARD
Road health              Road ranking
Damage clusters          Predictions
Reports                  Explainable priorities
Trends                   Maintenance actions
```

## 3. Core Innovation Stack

| Layer | Purpose | Contribution |
|---|---|---|
| Perception | Detect visible road damage | Existing YOLOv8 + RDD2022 |
| Evidence | Determine whether observations corroborate a real defect | Spatial, temporal and community fusion |
| Intelligence | Understand road condition over time | Road Health Score + Deterioration Index |
| Decision | Turn intelligence into action | Predictive maintenance prioritization |

## 4. Data Model

### 4.1 Reports

The citizen-facing report remains the raw observation submitted by a user. It should not itself be treated as the road-health entity.

```
Report
  id
  image_path
  latitude
  longitude
  timestamp
  source
  description
  community_upvotes
  verification_score
  status
  created_at
```

### 4.2 Detections

Every model detection should be stored separately so that one image can contain multiple defects.

```
Detection
  id
  report_id
  damage_type
  confidence
  bbox_x1
  bbox_y1
  bbox_x2
  bbox_y2
  bbox_area_ratio
  severity
```

### 4.3 Road Segments

The road segment is the primary intelligence entity in RoadTwin. It aggregates observations and maintains the current state of a physical road section.

```
RoadSegment
  id
  segment_identifier
  start_lat
  start_lng
  end_lat
  end_lng
  road_name
  road_type
  length_meters
  current_health_score
  current_risk_score
  deterioration_rate
  last_observed_at
```

### 4.4 Road Observations

```
RoadObservation
  id
  road_segment_id
  report_id
  detection_id
  observed_at
  severity
  damage_type
  confidence
  verification_score
  contribution_weight
```

### 4.5 Road Health and Prediction

```
RoadHealth
  road_segment_id
  measured_at
  health_score
  severity_burden
  damage_density
  evidence_score
  deterioration_rate
  risk_score

Prediction
  road_segment_id
  generated_at
  horizon_days
  predicted_health_score
  failure_probability
  confidence
```

### 4.6 Maintenance Recommendation

```
MaintenanceRecommendation
  road_segment_id
  priority_score
  urgency
  recommended_action
  generated_at
  explanation
```

## 5. Input Specification

| Input | Source | Required? | Purpose |
|---|---|---|---|
| Image | Citizen | YES | YOLO perception |
| Latitude | GPS / manual pin | YES | Spatial association |
| Longitude | GPS / manual pin | YES | Spatial association |
| Timestamp | System | YES | Temporal deterioration |
| Description | Citizen | Optional | Additional context |
| Community votes | Users | Generated | Evidence fusion |
| Damage type | YOLO | Generated | Damage classification |
| Confidence | YOLO | Generated | Model evidence |
| Bounding box | YOLO | Generated | Severity features |
| Road segment | Spatial engine | Generated | Road-level aggregation |
| Health score | Road Health Engine | Generated | Current condition |
| Deterioration rate | Health Engine | Generated | Trend |
| Risk score | Predictive Engine | Generated | Future risk |
| Priority score | Decision Engine | Generated | Maintenance ranking |

## 6. Road Health Score

The existing bounding-box severity calculation is retained as an observation-level feature. RoadTwin then aggregates multiple signals into a road-level score. The exact weights must be validated experimentally rather than presented as universally optimal.

```
RHS = 100 - DamageBurden

DamageBurden =
  w1 * SeverityBurden
+ w2 * DamageDensity
+ w3 * TemporalDeterioration
+ w4 * EvidenceBurden
```

**Suggested interpretation**

| Score | Interpretation |
|---|---|
| 80-100 | Excellent / healthy |
| 60-79 | Good / moderate monitoring |
| 40-59 | Poor / maintenance planning |
| 20-39 | Critical / urgent attention |
| 0-19 | Severely degraded / immediate intervention |

## 7. Deterioration Intelligence

A road becomes interesting when its condition changes over time. RoadTwin therefore stores longitudinal observations and computes a deterioration rate from health-score changes.

```
Deterioration Rate =
  (HealthScore_t2 - HealthScore_t1) / elapsed_time
```

Example:

```
Day 1  -> 82
Day 15 -> 73
Day 30 -> 61
Day 45 -> 48
```

Interpretation: The road is rapidly deteriorating.

## 8. Predictive Engine

Do not begin with a complex deep-learning forecasting model. The first implementation should establish a reliable longitudinal data pipeline and use a transparent baseline forecasting method. A more advanced model can be evaluated only after enough temporal data exists.

```
Road health history
        |
        v
Trend estimation
        |
        v
Forecast at 30 / 60 / 90 days
        |
        v
Predicted health + future risk
```

## 9. Evidence Fusion

YOLO confidence should not be treated as real-world certainty. RoadTwin combines model evidence with independent observations, spatial agreement, temporal consistency and community validation.

```
EvidenceScore =
  f(
    MLConfidence,
    ObservationCount,
    SpatialAgreement,
    TemporalConsistency,
    CommunityValidation
  )
```

## 10. Spatial Intelligence

Spatial clustering serves two purposes: first, merge likely duplicate citizen reports; second, aggregate observations into meaningful road segments. DBSCAN is a practical starting point for point clustering. Road-network-aware segmentation can be added when reliable road geometry is available.

```
50 citizen reports
        |
        v
17 individual detections
        |
        v
6 damage clusters
        |
        v
3 road segments
```

## 11. Maintenance Decision Engine

The final output is not a map of potholes. It is a ranked maintenance queue. Candidate inputs include severity, deterioration rate, damage density, evidence confidence, traffic exposure, road importance, nearby vulnerable locations and time since repair.

```
PriorityScore =
  f(
    Severity,
    DeteriorationRate,
    DamageDensity,
    EvidenceConfidence,
    TrafficExposure,
    RoadImportance,
    VulnerableLocationProximity,
    RepairRecency
  )
```

## 12. Dashboard Design

| Dashboard area | Primary information |
|---|---|
| Network overview | Overall health, critical roads, rapidly deteriorating roads, predicted failures |
| Road health map | Road-segment condition, risk and deterioration trend |
| Priority queue | Ranked roads with urgency and recommended action |
| Road detail | Health history, damage composition, evidence and forecast |
| Explainability | Why the road received its priority score |

## 13. Implementation Architecture

```
backend/
|
+-- models/
|   +-- report.py
|   +-- detection.py
|   +-- road_segment.py
|   +-- road_observation.py
|   +-- road_health.py
|   +-- prediction.py
|
+-- services/
|   +-- ml_service.py
|   +-- severity.py
|   +-- spatial/
|   |   +-- clustering.py
|   |   +-- segmentation.py
|   +-- intelligence/
|   |   +-- evidence.py
|   |   +-- health_score.py
|   |   +-- deterioration.py
|   |   +-- prediction.py
|   |   +-- priority.py
|   +-- maintenance/
|       +-- optimizer.py
|
+-- routes/
    +-- reports.py
    +-- roads.py
    +-- predictions.py
    +-- maintenance.py
    +-- map.py
    +-- admin.py
    +-- auth.py
```

Note: `MaintenanceRecommendation` (§4.6) has no dedicated model file listed in this original module sketch — planning should add `models/maintenance_recommendation.py` alongside the six listed model files to cover all seven entities.

## 14. Required External / Contextual Inputs

These should be treated as enhancement inputs, not blockers for the MVP.

| Input | Why it matters |
|---|---|
| Traffic / average daily traffic | Improves exposure and risk estimation |
| Rainfall / weather | Useful for deterioration modeling |
| Road classification | Separates highways, arterials, residential roads, etc. |
| Road age / construction history | Adds lifecycle context |
| Repair history | Allows before/after and time-since-repair analysis |
| Nearby schools / hospitals / intersections | Adds vulnerability context |

## 15. RoadTwin Dataset Strategy

RDD2022 remains the perception benchmark. The novel layer requires longitudinal, geospatial observations. We should therefore build a RoadTwin dataset in which repeated observations are associated with the same physical road segment over time.

```
RoadTwin Dataset

RoadID | Time  | Latitude | Longitude | Damage  | Severity | Confidence
R001   | Day1  | ...      | ...       | Crack   | Low      | ...
R001   | Day15 | ...      | ...       | Crack   | Medium   | ...
R001   | Day30 | ...      | ...       | Mesh    | High     | ...
R001   | Day45 | ...      | ...       | Pothole | Critical | ...
```

## 16. Implementation Order

1. Lock the database schemas and data contracts.
2. Keep the existing YOLO/RDD2022 inference pipeline as the perception baseline.
3. Persist every detection rather than only the final report-level result.
4. Implement GPS-based duplicate clustering and road-segment association.
5. Build the longitudinal RoadObservation history.
6. Implement and validate the Road Health Score.
7. Implement deterioration-rate estimation.
8. Build the initial transparent forecasting baseline.
9. Implement maintenance priority scoring and explanations.
10. Build the authority dashboard around road segments, trends and priorities.
11. Only then add external inputs such as traffic and weather if they materially improve evaluation.

## 17. What We Should NOT Do

- Do not replace YOLO merely to claim novelty.
- Do not add many disconnected AI features.
- Do not claim the severity thresholds are scientifically optimal without validation.
- Do not build a complex forecasting model before collecting longitudinal observations.
- Do not make traffic, weather or other external data mandatory for the first working system.
- Do not treat a citizen report as equivalent to a physical road defect without evidence fusion.

**Locked direction:** RoadTwin is a road-segment intelligence system. YOLO detects what is visible; RoadTwin determines what the road's condition means, how it is changing, what may happen next, and what should be fixed first.

---
*Transcribed into the repository: 2026-09-22, during Phase 1 planning, after research surfaced that this spec was referenced but never actually committed.*
