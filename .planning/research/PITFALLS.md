# Pitfalls Research

**Domain:** Predictive road-health / maintenance-intelligence systems (crowdsourced geotagged reporting + CV detection + spatial clustering + time-series health scoring + forecasting + government dashboard)
**Researched:** 2026-09-22
**Confidence:** MEDIUM (web-search-corroborated across multiple independent queries + domain-pattern analysis; no single authoritative "RoadTwin-shaped" post-mortem exists, so findings are synthesized from adjacent domains: civic-tech reporting platforms (FixMyStreet, SeeClickFix, StreetBump), ML calibration literature, DBSCAN/geospatial clustering literature, predictive-maintenance/IoT literature, structural-health-monitoring literature, and government-dashboard-trust literature)

## Validation of PROJECT.md's Existing Out-of-Scope Calls

Before adding new pitfalls, the following pre-empted decisions in PROJECT.md were checked against domain research and are **confirmed correct**:

| PROJECT.md decision | Research verdict |
|---|---|
| No deep-learning forecasting model until longitudinal data exists | **Confirmed critical.** Predictive-maintenance literature consistently identifies data scarcity / unrepresentative failure history as the #1 cause of PdM ML failure ("Strategies for overcoming data scarcity... in ML models for predictive maintenance," Nature Sci Reports 2024; ResearchGate "Predictive Maintenance without historical failure data?"). A trend-based baseline is the right v1 call. |
| Evidence score ≠ raw YOLO confidence alone | **Confirmed critical.** ML calibration literature is explicit: "model confidence and event probability are not the same thing — conflating them is one of the most common silent failures in production ML" (Medium/Data Science Collective, "Calibration in Production ML: Why Confidence Scores Lie"). Calibration is distinct from accuracy — a model can be accurate on average while individual confidence scores are systematically wrong for specific subpopulations (e.g., poor lighting, unusual damage types, camera angle). |
| DBSCAN (not road-network-geometry segmentation) as v1 | **Reasonable, but under-specified.** Research confirms DBSCAN is a legitimate practical starting point, but flags a real limitation the project should be aware of going in: DBSCAN assumes roughly uniform density and a single fixed epsilon, which breaks down on real GPS data where reporting density varies by neighborhood/road type (rural single-lane roads vs. dense urban intersections) — "DBSCAN is inappropriate for clusters with various densities, since epsilon is fixed... a catch-22: increase epsilon and it merges unrelated groups, decrease it and legitimate reports become noise" (multiple DBSCAN-tuning sources, cross-corroborated). This is not a reason to abandon DBSCAN for v1, but it is a reason to treat epsilon as a *per-road-class* tunable, not a single global constant, from day one — see Pitfall 3 below. |
| RHS/priority weights not presented as scientifically validated | **Confirmed correct instinct**, and directly connects to Pitfall 6 (dashboard trust) below — government dashboard trust research finds that dashboards "claiming perfect certainty" erode credibility faster than ones that visibly acknowledge limitations. |
| External inputs (traffic/weather/repair-history) as enhancement-only, never a blocker | **Confirmed correct** — consistent with the broader predictive-maintenance lesson that additional signal sources are best treated as optional enrichments once the core pipeline is proven, not prerequisites. |

**Gap identified:** PROJECT.md's Out of Scope section addresses *forecasting complexity* and *confidence conflation* but does **not yet address**: (1) anti-spam/malicious-submission defenses for the citizen-reporting surface, (2) GPS accuracy as a hard numeric constraint that should drive the DBSCAN epsilon choice, (3) cluster/segment ID instability across re-clustering runs, (4) cold-start display logic (what the dashboard shows before a segment has enough evidence), and (5) explainability/trust design for the authority-facing dashboard beyond "don't overclaim." These are addressed as new pitfalls below.

---

## Critical Pitfalls

### Pitfall 1: Treating Crowdsourced Reports as Verified Facts at Ingestion Time

**What goes wrong:**
A citizen submission (image + GPS + timestamp) gets written into the pipeline with the same status as a corroborated, multi-source-confirmed defect. Spam, joke submissions, GPS-spoofed reports, and simple noise (a photo of a train track mistaken for a pothole, a stale cached GPS fix) flow downstream with no distinguishing marker, and by the time they reach health scoring they are indistinguishable from real signal.

**Why it happens:**
Early architecture tends to optimize for "get the report in the database" and defers trust/validation to a later phase that never gets built, because it doesn't feel like part of the "real" intelligence pipeline. Boston's StreetBump app hit this directly in production — officials were dissatisfied because the sensor-based system "couldn't tell the difference between a real pothole and a train track," and it took an explicit ML-filtering layer to reduce false positives (MIT Technology Review; multiple corroborating sources).

**How to avoid:**
- Every `Report` and `Detection` should carry a status/trust lifecycle from the schema phase onward (e.g., `unverified → corroborated → evidence-confirmed`), not just an evidence *score* bolted on later — the score alone doesn't stop a single spam report from participating in RoadSegment aggregation before it's discounted.
- Apply cheap, cost-free filters at ingestion before anything touches the intelligence pipeline: rate limiting per device/account, minimum time-between-reports for the same GPS point (StreetBump-style submission cooldowns), EXIF/timestamp sanity checks (photo taken recently, not reused), and a plausibility check that the YOLO detector actually found *something* in the image before a report is allowed to count as a "damage" report vs. a general note.
- Keep raw ingestion (Report, Detection) fully separated from the evidence-fusion output (already true per PROJECT.md's entity list) — the mistake is not lacking an evidence score, it's letting unverified data flow into segment/health aggregation with equal weight before fusion runs.

**Warning signs:**
- A single low-corroboration report can visibly move a segment's health score or priority rank.
- No account/device-level submission-rate telemetry exists — you'd only discover spam abuse after a dashboard user notices a nonsensical ranking.
- QA/demo data has zero adversarial or noisy inputs (only "clean" test images) — the pipeline has never been stress-tested against garbage input.

**Phase to address:** Schema/persistence phase (status lifecycle in the data model) and detection-persistence phase (ingestion-time filters); reinforced at evidence-fusion phase.

---

### Pitfall 2: GPS Noise Treated as Exact Position

**What goes wrong:**
Consumer smartphone GPS has real, well-known error bounds — typically 5-10m in open sky, degrading to 20-50m+ in urban canyons, under tree cover, or with a cold GPS fix. Systems that treat each report's lat/lon as ground truth will (a) fail to merge duplicate reports of the same physical defect because the points don't fall within an arbitrarily tight radius, and (b) misattribute a report to the wrong road segment entirely at intersections, highway on/off-ramps, or divided roads with parallel carriageways.

**Why it happens:**
GPS coordinates *look* precise (many decimal places) so it's easy to treat them as precise. The error is invisible until you compare two independent reports of the same physical pothole and find they're 30 meters apart.

**How to avoid:**
- Set DBSCAN epsilon based on the actual expected GPS error distribution for the device/context, not an arbitrary round number — and treat it as configurable per road class (dense urban grid vs. rural highway) rather than one global constant, directly answering the density-variance limitation noted above.
- Capture and persist GPS accuracy/horizontal-error-radius metadata from the device when available (most mobile geolocation APIs expose this) — use it as a per-point weight in clustering and evidence fusion, not just the raw coordinate.
- For segment assignment near intersections/parallel roads, don't rely on nearest-point-only logic; snapping ambiguity should lower evidence confidence rather than silently picking a segment.

**Warning signs:**
- Two citizen reports of visibly the same pothole (same photo angle, same timestamp window) end up in different clusters/segments.
- Reports cluster suspiciously exactly on road centerlines with zero perpendicular scatter (suggests reports are being snapped/rounded rather than reflecting real device noise) — or the opposite, wild scatter with no clustering ever succeeding.
- Manual-pin reports (no device GPS) are stored identically to auto-GPS reports with no accuracy differentiation.

**Phase to address:** Schema/persistence phase (capture accuracy metadata at ingestion) and clustering phase (epsilon tuning, per-class parameters).

---

### Pitfall 3: DBSCAN Clusters Are Not Stable Across Re-Runs, and Cluster IDs Get Silently Reassigned

**What goes wrong:**
DBSCAN re-run on an updated point set (new reports keep arriving) can produce different cluster boundaries than the previous run — a new report can bridge two previously-separate clusters into one, or noise points can suddenly qualify as core points. If RoadSegment identity is derived naively from cluster output each time, segment IDs "shift," and the longitudinal `RoadObservation` history the whole health/deterioration/forecast pipeline depends on gets silently broken — a segment's history appears to start over, or two segments' histories merge.

**Why it happens:**
DBSCAN clustering and persistent entity identity are two different problems that look like the same problem. It's natural to run clustering and treat its output directly as "the segments," without a stable identity/merge-reconciliation layer between the raw clustering pass and the persisted `RoadSegment` entity.

**How to avoid:**
- Treat DBSCAN output as *candidate* clusters, and add an explicit reconciliation step that maps new clustering results onto existing persisted `RoadSegment` IDs (by spatial overlap / centroid proximity), rather than re-minting segment identity on every clustering run.
- Log and make auditable every segment split/merge event — this is the exact class of silent data corruption that later shows up as "the health score history for this road looks wrong" with no way to explain why.
- Run clustering as an incremental/idempotent process where possible (assign new points to existing segments first; only spawn new segments or trigger a re-cluster when points don't fit any existing segment within tolerance).

**Warning signs:**
- A `RoadObservation` history for a segment has a sudden, unexplained gap or discontinuity in observation count with no correlated event.
- Segment count changes significantly between clustering runs on data that only grew incrementally.
- No test exists for "add one report near a cluster boundary, verify existing segment IDs are preserved."

**Phase to address:** Clustering phase (design the reconciliation layer up front, not as a later fix) — this is one of the highest-cost-to-retrofit pitfalls in the whole system because deterioration rate and forecasting both depend on segment identity being stable over time.

---

### Pitfall 4: Health Score / Deterioration Rate Computed on Sparse, Irregular Observation Data as if It Were a Regular Time Series

**What goes wrong:**
The deterioration formula `(HealthScore_t2 − HealthScore_t1) / elapsed_time` looks like simple arithmetic, but citizen reporting is bursty and irregular — a segment might get five reports in one week (after a viral local complaint) and then nothing for two months. Naively computing deterioration between the two nearest observations produces wildly unstable, noise-dominated rates: a short elapsed_time with a modest score difference produces an extreme (and meaningless) rate; a long gap can average away a real rapid decline into a falsely gentle slope.

**Why it happens:**
The formula is correct in principle but is being applied to data that violates its implicit assumption of reasonably regular, representative sampling — a problem well documented in structural-health-monitoring and clinical time-series literature ("sparsity and irregularity pose a significant challenge... requiring uniform time series generation for successful analysis," multiple corroborating sources on irregular-time-series interpolation).

**How to avoid:**
- Never compute deterioration rate from exactly two raw points without a minimum observation count and minimum elapsed-time floor; below that threshold, report "insufficient data" rather than a number.
- Use a smoothing/robust-trend approach (e.g., weighted rolling regression over available observations, not point-to-point delta) once there are enough observations — this is still "transparent trend-based," consistent with PROJECT.md's forecasting constraint, just numerically more robust than naive two-point slope.
- Surface observation density/recency explicitly wherever a deterioration rate or forecast is displayed — a rate computed from 2 sparse points 90 days apart needs a visibly different confidence treatment than one computed from 8 evenly-spaced points.

**Warning signs:**
- Deterioration rates that swing from strongly negative to strongly positive between consecutive recomputations as single new reports arrive.
- Segments with only 1-2 historical observations showing deterioration rates and forecasts with no visible caveat.
- No minimum-evidence gate exists before a segment is allowed to show a numeric trend at all.

**Phase to address:** Health-scoring phase (design the minimum-observation gate into the formula, not the dashboard) and deterioration/forecast-baseline phase.

---

### Pitfall 5: Forecasting Feature Ships Before There's Enough Data to Validate It Against, and Nobody Notices Because It "Looks" Fine

**What goes wrong:**
Even a transparent trend-based forecast (the correct v1 choice per PROJECT.md) can quietly produce garbage on low-data segments — extrapolating a two-point slope 30/60/90 days into the future amplifies the sparse-data instability from Pitfall 4. The danger isn't building a deep-learning model too early (already correctly out of scope); it's that even the *simple* baseline can be shown for segments that don't have enough history to justify any forecast at all, and there's no historical outcome data yet to check whether the forecast was ever right.

**Why it happens:**
"We're using a simple transparent method, so it's safe" is a false sense of security — a linear extrapolation from noise is still noise, just noise with an explainable formula. Predictive-maintenance literature is consistent on this exact failure mode: models (simple or complex) built on unrepresentative/limited historical data generalize poorly and are essentially unvalidatable until real outcomes accumulate (Nature Sci Reports 2024, ResearchGate).

**How to avoid:**
- Gate forecast display behind the same minimum-observation/minimum-timespan threshold as deterioration rate (Pitfall 4) — "not enough data yet" is a legitimate and honest dashboard state, not a failure to fix.
- Track forecast accuracy retroactively from day one: whenever a segment gets a new observation, compare it against what the 30/60/90-day forecast made N days earlier predicted. Without this, there is no way to know if the trend baseline is even directionally useful, and no evidence base to eventually justify a more sophisticated model.
- Resist pressure to add seasonality, external covariates (weather/traffic), or nonlinear terms to "improve" the baseline before there's enough validated history — each added parameter needs more data to avoid overfitting noise, which is the opposite of what's available early on.

**Warning signs:**
- Forecasts are shown for every segment uniformly, with no visible distinction between a segment with rich history and one with two observations.
- No forecast-vs-actual tracking mechanism exists anywhere in the system.
- Feature requests start arriving for "smarter" forecasting before a single forecast has been checked against reality.

**Phase to address:** Forecast-baseline phase (build the accuracy-tracking mechanism alongside the forecast itself, not after) and dashboard phase (visible confidence/data-sufficiency indicator per forecast).

---

### Pitfall 6: Authority Dashboard Presents Ranked Priority as Objective Fact, Undermining the Trust It Needs to Drive Real Budget Decisions

**What goes wrong:**
A ranked maintenance queue with a single priority number per road segment is easy to build and satisfying to demo, but if it's presented without visible uncertainty, evidence basis, or the ability to drill into *why* a segment ranked where it did, it either (a) gets rejected by skeptical officials who don't trust a black-box ranking for budget decisions, or (b) gets trusted uncritically and used to justify decisions the underlying evidence doesn't actually support — both are failure modes, and the second is arguably worse for a civic system. Government-dashboard research is explicit here: "inconsistent, incomplete, or poorly defined data threatens the credibility of any dashboard... dashboards that explain how data is collected and what it cannot tell you are paradoxically more credible than those claiming perfect certainty," and "many dashboards are launched and then forgotten... adoption is constrained by skepticism about generic solutions designed without user input" (cross-corroborated government-dashboard-trust sources).

**Why it happens:**
Explainability is treated as a nice-to-have UI feature added at the end, rather than a load-bearing requirement of the underlying data model. If evidence score, observation count, spatial agreement, and temporal consistency aren't already tracked as distinct, queryable fields (which PROJECT.md's entity model correctly anticipates), there's nothing for the dashboard to explain — explainability can't be retrofitted onto an opaque score.

**How to avoid:**
- Every priority score and health score shown to an authority user must be paired with a human-readable "why" breakdown (already an Active requirement in PROJECT.md) — treat this as a hard dependency of the dashboard phase, not a stretch goal.
- Visibly surface data sufficiency/confidence per segment (evidence burden, observation count, recency) directly in the ranked queue, not buried in a detail page — a segment ranked #1 on thin evidence should look different at a glance from one ranked #1 on strong evidence.
- Involve actual target users (road-authority staff) before the dashboard is finalized — generic "we built you a dashboard" tools are exactly what the civic-tech literature flags as low-adoption; validate against how maintenance decisions are actually made and funded today.
- Never let the dashboard imply the RHS/priority weighting is a validated, authoritative formula (already correctly called out in PROJECT.md's Out of Scope) — say so explicitly in the UI, since honest limitation-disclosure is the credibility-builder per the research, not a liability to hide.

**Warning signs:**
- Stakeholder demo feedback is "looks impressive" rather than "I could act on this."
- No path exists in the UI from a ranked segment down to the individual observations/detections/reports backing its score.
- The dashboard was designed and built without any road-authority user in the loop.

**Phase to address:** Priority-scoring phase (structure the explanation data) and dashboard phase (surface it, gate on real-user validation before considering the phase done).

---

### Pitfall 7: Evidence-Fusion Formula Weights Are Guessed Once and Never Revisited

**What goes wrong:**
The evidence score combines ML confidence, observation count, spatial agreement, temporal consistency, and community validation — a reasonable design — but if the relative weights are chosen once during initial development and hard-coded, they silently calcify into "the algorithm" even though PROJECT.md correctly acknowledges they're placeholders. Over time, as real usage patterns diverge from the assumptions made at design time (e.g., community upvotes turn out to be gameable, or a particular damage type is systematically under-detected by YOLO), the formula keeps producing confident-looking numbers that are quietly wrong in a specific, correctable way nobody is checking for.

**Why it happens:**
Once a scoring formula ships and looks reasonable in a demo, there's little organic pressure to revisit it — especially because, unlike a forecast, there's no obvious "was this right?" feedback loop unless one is deliberately built.

**How to avoid:**
- Make evidence-score weights configuration, not constants baked into code, from the schema/evidence-fusion phase onward — this is cheap now and expensive to retrofit later.
- Log the component inputs (not just the final score) for every evidence-score computation, so weight assumptions can be audited and re-tuned against real outcomes later (e.g., once repair records confirm which flagged segments actually had confirmed defects).
- Revisit weight validation explicitly at a milestone boundary once enough repair-confirmation data exists — this is a natural, low-risk place to eventually retire the "not scientifically validated" caveat for specific components, rather than all at once.

**Warning signs:**
- Evidence score formula has no versioning — can't tell which weights produced a historical score.
- No mechanism exists to compare evidence score against eventual ground truth (confirmed repair, inspector visit, etc.).

**Phase to address:** Evidence-fusion phase (make weights configurable + log components); revisited at milestone boundaries, not a single phase.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Deriving RoadSegment identity fresh from each DBSCAN run instead of building a reconciliation layer | Faster to ship clustering phase | Breaks longitudinal observation history (Pitfall 3), which the entire health/deterioration/forecast pipeline depends on | Never past the clustering phase — this is foundational, not deferrable |
| Hard-coding evidence-score / RHS / priority weights as constants | Faster initial implementation | Formula calcifies unaudited (Pitfall 7); no path to responsible re-tuning | Acceptable for the very first prototype pass only, must become configuration before dashboard phase ships to real users |
| Computing deterioration rate from raw two-point delta with no minimum-data gate | Simpler formula, ships faster | Wildly unstable, misleading rates on sparse segments (Pitfall 4) | Never for anything shown to authority users; fine for internal dev/debug views only |
| Skipping ingestion-time anti-spam/rate-limit checks in early build | Faster path to a working demo | Garbage-in propagates through fusion/clustering/scoring with no clean way to retroactively identify and exclude it | Acceptable only pre-public-launch; must exist before real citizen traffic |
| Single global DBSCAN epsilon for all road types | Simpler tuning, one config value | Under-merges sparse rural reports or over-merges dense urban ones (Pitfall 2/PROJECT.md's own flagged DBSCAN limitation) | Acceptable for first prototype on a single test region; revisit before multi-region rollout |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-------------------|
| Mobile device Geolocation API | Trusting raw lat/lon with no accuracy field, treating a stale cached fix as fresh | Capture and persist the accuracy/error-radius the API exposes; reject or flag fixes with accuracy worse than a defined threshold |
| YOLOv8 / RDD2022 inference | Treating `confidence` output as P(real defect), applying one global confidence threshold across all damage classes | Treat confidence as model certainty only; validate/calibrate per damage class since RDD2022 classes are not equally easy to detect, and feed raw confidence into evidence fusion, not directly into user-facing certainty language |
| Leaflet map rendering | Rendering every raw point/report on the public map at all zoom levels, causing visual clutter and implying every point is an independent confirmed issue | Cluster/aggregate for display at the RoadSegment level (matches the architecture's own entity model); raw points are backing detail, not the primary visual unit |
| Image upload / storage | No validation that an uploaded "road photo" actually contains a road/relevant scene before it consumes YOLO inference cost and enters the pipeline | Lightweight pre-filter or rely on YOLO's own no-detection case to short-circuit irrelevant images early, and don't create a Report-level record implying content that isn't there |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Re-running full DBSCAN over the entire point set on every new report | Slower ingestion as report volume grows; clustering becomes a bottleneck | Incremental assignment of new points to existing segments first; full re-cluster only periodically or on-demand | Noticeable once report volume reaches the thousands within a metro area |
| Recomputing health score / deterioration for all segments on every write | Unnecessary compute, slows down write path | Recompute only for the affected segment(s) on new observation; batch/async recompute for network-wide aggregates | Becomes visible once segment count is in the hundreds-thousands with frequent report inflow |
| Dashboard priority-queue query joining raw Report/Detection tables live on every page load | Slow dashboard load times as historical data accumulates | Materialize RoadHealth/priority as precomputed, periodically refreshed read tables (not computed live from raw observations each request) | Breaks once historical data spans months and detection counts are in the tens of thousands |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No GPS-spoofing/replay defense on report submission | Bad actors can fabricate a false road-damage pattern in a specific area (e.g., to manipulate which roads get budget priority) | Rate-limit and flag anomalous submission patterns (impossible travel speed between consecutive reports from one device, identical images re-submitted with different GPS); treat spoofing risk as elevated specifically *because* this data drives real government budget decisions |
| No image-reuse/tamper detection | Same photo re-submitted at different locations to fabricate report volume, inflating a segment's apparent evidence | Perceptual-hash duplicate detection across the image corpus, not just GPS-based duplicate detection |
| Treating community upvotes as unforgeable signal | Small number of coordinated accounts can inflate community validation weight in evidence fusion (Pitfall 7's "gameable" concern) | Weight community validation by account diversity/reputation, not raw upvote count; cap influence of new/unverified accounts |
| No audit trail on segment split/merge or weight-config changes | Silent data integrity issues (Pitfall 3) become unexplainable and undebuggable, and are also a real accountability gap if a government body relies on this data for spending decisions | Log every segment reconciliation event and every scoring-weight change with who/when/why |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Public map shows every raw citizen report as an equally-weighted pin | Citizens/public misread report density as confirmed severity; spam or single unconfirmed reports look identical to well-corroborated defects | Distinguish visually between "reported, unconfirmed" and "evidence-confirmed" states; aggregate at segment level as the primary view |
| Authority dashboard shows a single priority number with no breakdown | Officials either reject the tool as a black box or over-trust a number they can't interrogate (Pitfall 6) | Every ranked item must be one click from its evidence breakdown |
| Forecast shown identically regardless of underlying data sufficiency | Users can't tell a well-supported trend from a two-point guess, leading to misplaced confidence or, once burned, complete distrust of all forecasts | Visible confidence/data-sufficiency badge tied to observation count and timespan, gated per Pitfall 4/5 |
| No path for a citizen or official to report an incorrect detection/mismerge | Errors compound silently (a garbage report keeps influencing a segment indefinitely) | Provide a correction/dispute mechanism feeding back into the report status lifecycle from Pitfall 1 |

## "Looks Done But Isn't" Checklist

- [ ] **Duplicate detection:** Often only handles near-identical GPS coordinates — verify it also handles the "same pothole, two different manual pins 20m apart" case and the "cluster boundary reassignment" case (Pitfall 3).
- [ ] **Evidence score:** Often computed correctly for well-populated segments but silently divides-by-zero or defaults to a misleading high/low value on segments with a single observation — verify the minimum-evidence floor exists.
- [ ] **Deterioration rate / forecast:** Often works in the demo (curated, well-spaced test data) but breaks down on real sparse/bursty data — verify against genuinely irregular observation spacing, not just clean synthetic sequences.
- [ ] **Dashboard explainability:** Often present as a static "methodology" page but not wired to actually explain a *specific* segment's *specific* score — verify the drill-down path is functional per-segment, not just documented in the abstract.
- [ ] **Anti-spam:** Often "we'll add it later" — verify basic rate-limiting/plausibility checks exist before any real public-facing launch, not just before a specific milestone deadline.
- [ ] **Segment identity stability:** Often untested — verify there's an actual test that adds new reports over multiple clustering runs and confirms existing segment IDs and their observation histories survive intact.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|------------------|
| Segment ID instability discovered after data has accumulated (Pitfall 3) | HIGH | Requires a one-time reconciliation migration: snapshot current clusters, manually/heuristically map old fragmented histories onto corrected stable segment IDs, backfill observation history; painful but must be done once rather than repeatedly |
| Spam/garbage reports already in the dataset (Pitfall 1) | MEDIUM | Retroactive filtering pass using whatever plausibility/rate-limit heuristics should have existed at ingestion; flag affected historical evidence scores as needing recomputation rather than trusting them |
| Evidence-score weights found to be badly miscalibrated after real-world validation (Pitfall 7) | MEDIUM | Because weights should be configuration (not hard-coded) and components should be logged separately, recomputation from logged components is possible without re-deriving from scratch — this is exactly why component-logging matters up front |
| Dashboard trust already damaged by an unexplained/overconfident ranking shown to officials (Pitfall 6) | HIGH | Trust is the hardest thing to recover in a civic-tech context; requires transparent post-hoc explanation, visible correction, and likely a slower re-introduction with heavier caveats than would have been needed if done right the first time |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Reports treated as verified fact at ingestion | Schema/persistence + detection-persistence phase | Status lifecycle field exists on Report/Detection; ingestion-time rate-limit/plausibility filters demonstrably reject synthetic spam input |
| GPS noise treated as exact position | Schema/persistence + clustering phase | Accuracy metadata is captured and persisted; DBSCAN epsilon is configurable per road class, not a single hard-coded constant |
| DBSCAN cluster/segment ID instability | Clustering phase | Test: add incremental reports across multiple clustering runs, confirm existing segment IDs and observation histories are preserved |
| Health/deterioration computed on sparse data as if regular | Health-scoring + deterioration phase | Minimum-observation/minimum-timespan gate exists before a numeric deterioration rate is produced; below threshold returns explicit "insufficient data" |
| Forecasting shipped before validatable | Forecast-baseline phase | Forecast-vs-actual tracking mechanism exists and is populated from the first forecast onward; forecast display gated by same data-sufficiency threshold as deterioration |
| Dashboard overclaims certainty / lacks explainability | Priority-scoring + dashboard phase | Every ranked segment has a functional drill-down to its evidence breakdown; real road-authority users have reviewed the dashboard before considering the phase done |
| Evidence-fusion weights guessed once, never revisited | Evidence-fusion phase | Weights are configuration, not constants; component inputs are logged per computation, enabling later re-tuning against real outcomes |

## Sources

- MIT Technology Review, "Road Repair via Crowdsourcing" (StreetBump false-positive/train-track problem) — https://www.technologyreview.com/2011/05/13/88309/road-repair-via-crowdsourcing/
- ResearchGate, "By the people, for the people: the crowdsourcing of 'streetbump'" — https://www.researchgate.net/publication/275329755_By_the_people_for_the_people_the_crowdsourcing_of_streetbumpan_automatic_pothole_mapping_app
- Civic Tech Field Guide (via SlideShare), "Knowledge from failure" — https://www.slideshare.net/mysociety/knowledge-from-failure-learnings-from-the-civic-tech-field-guide-matt-stempeck-and-micah-l-sifry-civic-hall
- Grokipedia, "FixMyStreet.com" — https://grokipedia.com/page/fixmystreetcom
- Medium / Data Science Collective, "Calibration in Production ML: Why Confidence Scores Lie" — https://medium.com/data-science-collective/calibration-in-production-ml-why-confidence-scores-lie-03f646796a35
- Google PAIR, "Are Model Predictions Probabilities?" — https://pair.withgoogle.com/explorables/uncertainty-calibration/
- Medium, "Are you really that sure? Calibration of deep neural networks" — https://medium.com/@romoflow/are-you-really-that-sure-a086b0ab9b78
- HDBSCAN docs, "Combining HDBSCAN* with DBSCAN" (variable-density limitation of fixed-epsilon DBSCAN) — https://hdbscan.readthedocs.io/en/latest/how_to_use_epsilon.html
- SciELO, "An Adaptative Eps Parameter of DBSCAN Algorithm for Identifying Clusters with Heterogeneous Density" — https://www.scielo.org.mx/scielo.php?script=sci_arttext&pid=S1405-55462024000200465
- Medium, "Multi-Feature Geo Clustering With DBSCAN" — https://medium.com/@sylvainma/multi-feature-geo-clustering-with-dbscan-4857c6b932e2
- Nature Scientific Reports (2024), "Strategies for overcoming data scarcity, imbalance, and feature selection challenges in ML models for predictive maintenance" — https://www.nature.com/articles/s41598-024-59958-9
- ResearchGate, "Predictive Maintenance without historical failure data?" — https://www.researchgate.net/post/Predictive-Maintenance-without-historical-failure-data
- Medium, "The weak side of Predictive Maintenance" — https://medium.com/@slava.K./the-weak-side-of-predictive-maintenance-f2c3b129f4e5
- SpiderStrategies, "Government Dashboards: Transparency, Trust & Public Accountability" — https://www.spiderstrategies.com/blog/government-dashboards/
- CSM Tech, "Dashboards for Impact: What the Government Must Get Right About Data and Trust" — https://www.csm.tech/blog-details/dashboards-for-impact-what-the-government-must-get-right-about-data-and-trust
- ScienceDirect, "Data science empowering the public: Data-driven dashboards for transparent and accountable decision-making in smart cities" — https://www.sciencedirect.com/science/article/pii/S0740624X18300303
- MDPI (2025), "Uncovering Symmetric and Asymmetric Deterioration Patterns in Maryland's Steel Bridges Through Time-Series Clustering and PCA" (sparse/irregular infrastructure health-index interpolation) — https://doi.org/10.3390/sym17122074
- PMC, "Data-Driven Structural Health Monitoring and Damage Detection through Deep Learning: State-of-the-Art Review" — https://pmc.ncbi.nlm.nih.gov/articles/PMC7294417/
- arXiv, "Modeling Irregularly Sampled Clinical Time Series" (general irregular-time-series handling principles applied by analogy) — https://arxiv.org/pdf/1812.00531

Confidence note: These sources are drawn from adjacent domains (general civic-tech reporting, ML calibration theory, geospatial clustering theory, industrial predictive maintenance, structural/clinical time-series, government-dashboard trust research) and cross-corroborated across independent search queries — no single source addresses "RoadTwin" directly since it doesn't exist as a named prior project. Treat pitfall *existence and mechanism* as MEDIUM-HIGH confidence (strongly corroborated patterns across independent domains) and the specific *RoadTwin-phase mapping* as this agent's synthesis (informed by PROJECT.md's own architecture), not an independently sourced claim.

---
*Pitfalls research for: predictive road-health / maintenance-intelligence civic-tech systems*
*Researched: 2026-09-22*
