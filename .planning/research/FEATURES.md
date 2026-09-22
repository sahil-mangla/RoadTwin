# Feature Research

**Domain:** Crowdsourced civic-damage reporting + road/pavement asset-management + predictive-maintenance intelligence (RoadTwin's three overlapping reference categories)
**Researched:** 2026-09-22
**Confidence:** MEDIUM (web search, cross-checked across 7 independent queries against multiple named products — SeeClickFix, FixMyStreet, Cartegraph, StreetSaver, RoadBotics, generic 311/predictive-maintenance platforms; no primary vendor docs consulted, so feature depth is directional not exhaustive)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist across all three reference categories. Missing these makes the product feel incomplete or unusable at the civic-software trust bar.

| Feature | Why Expected | Complexity | Notes | PROJECT.md status |
|---------|--------------|------------|-------|--------------------|
| Geotagged photo report submission (image + GPS + timestamp + description) | Baseline of every civic reporting app (SeeClickFix, FixMyStreet, 311 apps) | LOW | Already in RoadTwin's MVP baseline | **Covered** — Active req #1 |
| Public map of reported issues | Universal across SeeClickFix/FixMyStreet/RoadBotics/PMS tools — citizens and staff both expect to see "what's been reported where" | LOW-MEDIUM | Leaflet already the fixed stack choice | **Covered** — Active req (public map) |
| Report status tracking (received → in progress → resolved) | Core 311/SeeClickFix expectation; citizens want to know their report didn't vanish | LOW-MEDIUM | Explicitly named as a distinct expectation in 311 research (tracking number / portal) | **Covered** — Active req (admin/repair workflow, status transitions) |
| Duplicate/near-duplicate detection and merging | Every 311 and civic-reporting system studied calls this out as core, not optional — prevents inflated counts and staff confusion | MEDIUM | RoadTwin already plans DBSCAN clustering, which is stronger than typical proximity-alert merging seen in competitors | **Covered** — Active req (DBSCAN merge) |
| Community upvote / "me too" signal | SeeClickFix and generic civic apps use this as lightweight crowd-validation to surface urgent issues | LOW | RoadTwin already folds this into evidence score, which is more rigorous than typical raw upvote counts | **Covered** — Active req (evidence score) |
| Automated status notifications to reporters | 311 apps send "received / assigned / resolved" messages as a baseline trust mechanism | LOW-MEDIUM | Not explicitly named in PROJECT.md Active list | **GAP — see below** |
| Citizen authentication / account identity (even lightweight, e.g. email or anonymous device ID) | Needed to prevent one person flooding duplicate reports, to attribute upvotes, and to notify on status change | LOW-MEDIUM | Not explicitly named in PROJECT.md Active list | **GAP — see below** |
| Admin/staff authentication and role separation (citizen vs. authority staff vs. super-admin) | Every reference system (SeeClickFix 311 CRM, StreetSaver, Cartegraph) gates the dashboard/priority-queue/status-transition actions behind authenticated staff roles — an authority dashboard with no access control is a non-starter for a government buyer | LOW-MEDIUM | PROJECT.md names an "authority dashboard" and "admin/repair workflow" but never states auth/roles as a requirement | **GAP — see below** |
| Spam / abuse rate limiting on submissions | Explicitly called out in civic-reporting research as a standard safeguard alongside duplicate detection | LOW | Not mentioned anywhere in PROJECT.md | **GAP — see below** |
| Basic moderator/report-verification step for flagrant abuse (fake photos, offensive content) | Research: "risk of misinformation... platforms employ moderators to verify reports" | LOW-MEDIUM | RoadTwin's evidence-fusion model partially substitutes for this (statistical corroboration rather than human moderation) but doesn't cover malicious/offensive content, which needs a manual flag-and-hide path | **PARTIAL GAP — see below** |
| Per-segment condition score on a published, interpretable scale (PCI-style 0-100) | Universal across StreetSaver, RoadBotics HD-PCI, Cartegraph — road authorities are trained on 0-100 PCI-style scales | LOW-MEDIUM | RoadTwin's Road Health Score (0-100, banded) matches this convention closely | **Covered** — Active req (RHS) |
| Network-level map colored/filterable by condition | Every PMS and RoadBotics-style tool provides this as the primary staff view | MEDIUM | **Covered** — Active req (authority dashboard road health map) |
| Exportable data (CSV or similar) for offline analysis / reporting to council or funders | RoadBotics and PMS tools explicitly support CSV export — government buyers routinely need this for grant reporting, council presentations | LOW | Not mentioned in PROJECT.md Active list | **GAP — minor, flag for later phase, not blocking v1** |

### Differentiators (Competitive Advantage)

These map directly onto what PROJECT.md already positions as RoadTwin's core value — validated as genuinely differentiating relative to the reference set, not table stakes.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Per-detection (not per-report) persistence with bbox/type/confidence | Reference civic-reporting apps (SeeClickFix/FixMyStreet) treat a report as one atomic unit; PMS tools log distress types but rarely at RoadTwin's per-bounding-box granularity tied back to a specific citizen photo | MEDIUM | Directly matches PROJECT.md Active req; not seen as standard in any reference product — genuine differentiator |
| Evidence fusion (ML confidence + spatial agreement + temporal consistency + community validation, explicitly not equal to raw model confidence) | Predictive-maintenance research confirms "explainable maintenance platforms" trend but none of the researched consumer-facing civic tools do multi-signal evidence fusion — RoadBotics and StreetSaver rely on either pure AI score or pure human inspection, not fused citizen+AI+corroboration | HIGH | This is RoadTwin's most defensible differentiator vs. both civic-reporting apps (which trust raw reports) and PMS tools (which trust either inspectors or AI alone) |
| Longitudinal RoadObservation history per segment (repeated measurements over time, not single snapshot) | StreetSaver/Cartegraph do track PCI history for budget planning, so this is closer to table-stakes *within pavement-management-specifically*, but is a genuine differentiator vs. the civic-reporting-app category, which is snapshot-only | MEDIUM-HIGH | Frame as differentiator vs. citizen-reporting apps, near-parity vs. mature PMS tools — still valuable because it's citizen-data-driven rather than requiring paid inspection vehicles |
| Deterioration rate computation from health-score history | PMS tools do "projected future PCI" but typically via engineering decay-curve models calibrated on large historical paving datasets; RoadTwin computing this directly from its own fused observation stream (without needing that historical calibration dataset) is a leaner, faster-to-bootstrap approach | MEDIUM | Matches PROJECT.md's explicit choice to defer deep-learning forecasting — reinforces the "transparent trend baseline first" decision as sound and differentiated-enough for v1 |
| 30/60/90-day forecast per segment, transparent/non-black-box | Predictive-maintenance research confirms "explainability" is an emerging expectation in the broader predictive-maintenance space, but reference civic/PMS tools rarely expose a forecast at all — StreetSaver's "budget scenario" projections are network-level, not per-segment probabilistic forecasts | MEDIUM-HIGH | Matches PROJECT.md; genuinely ahead of the civic-reporting category, roughly at parity with sophisticated PMS budget tools but simpler/cheaper |
| Multi-factor maintenance priority score (severity + deterioration + density + evidence + traffic + importance + vulnerable-proximity + repair recency) with human-readable "why" explanation | Predictive-maintenance research confirms ranked priority queues with expected_loss × criticality weighting are the state of the art, and explicitly flags explainability/rationale-with-thresholds as the differentiator over "black box" scoring — this is precisely what road-authority dashboard users are shown to expect | HIGH | **This is the single most externally-validated differentiator.** Both the predictive-maintenance research and the government-dashboard research independently converge on: (1) a ranked queue answering "what first," (2) rule-based/threshold-driven rationale rather than opaque ML, (3) ability to sensitivity-test/see what's driving the rank. See dedicated section below. |
| Explainability specifically as a first-class dashboard feature (not an afterthought) | Cross-validated by both the predictive-maintenance-platform research and the government-road-prioritization research (see next section) | MEDIUM | Matches PROJECT.md Active req directly — strongly confirmed as a real expectation, not a nice-to-have |

### What Road-Authority / Government Dashboard Users Specifically Expect From a "Priority Queue" + Explainability

This is a targeted synthesis across the predictive-maintenance and government-prioritization research, since PROJECT.md leans heavily on this feature:

1. **Ranked list answering "what first," not just a score dump.** Research on predictive-maintenance platforms is explicit: a priority queue "lets managers inspect the highest-risk assets first" and "answers what first." A dashboard that shows scores without a sorted, actionable queue view falls short of this expectation.
2. **Weighted, multi-criteria composition — not a single number pretending to be objective.** Government road-prioritization research confirms authorities are used to methods ranging from simple subjective ranking to full multi-criteria optimization (traffic + condition + environmental/criticality factors). A one-dimensional "worst road first" ranking undersells what road authorities are trained to expect from professional PMS tools — RoadTwin's multi-factor priority score (severity, deterioration, density, evidence, traffic, importance, vulnerable-proximity, repair recency) matches this expectation well.
3. **Explicit rationale per item, with thresholds/priority classes, not opaque ML.** Predictive-maintenance research: "explainable maintenance platforms provide explainable maintenance actions with prioritization and impact context... rule-guided recommendations that have thresholds, priority classes, and explicit rationale." This directly validates PROJECT.md's Active requirement "every priority score has a human-readable explanation."
4. **Sensitivity/what-if testing on the weighting.** Government-dashboard research specifically calls out dashboards that let staff test different weighting scenarios and see how the ranking shifts (echoing StreetSaver's "budget scenario" modeling). RoadTwin's Active requirements do not currently include weight sensitivity-testing — flag as a plausible v1.x addition, not a v1 blocker, since PROJECT.md explicitly marks RHS/priority weights as "placeholders pending experimental tuning" (i.e., the weights themselves are expected to be provisional — a what-if view would make that transparency more actionable for staff, but isn't required to ship the core queue).
5. **Budget-conscious framing.** Multiple sources (government dashboard research, PMS research) emphasize that authorities think in terms of "what does my limited budget best cover" — e.g., the finding that majority preservation-first spending on decent-condition roads outperforms naive worst-first spending. RoadTwin's priority score doesn't currently model budget-constrained optimization (i.e., "given $X, which combination of repairs maximizes network health") — this is a reasonable **out-of-scope-for-v1** item, consistent with PROJECT.md's philosophy of deferring anything not yet needed for the first working system, but worth flagging as a natural v2 differentiator once the core ranked queue is validated.
6. **Drill-down from ranked item to full evidence trail.** PROJECT.md's "road detail (history/composition/evidence/forecast)" view matches this expectation precisely — road-authority users don't just want a rank, they want to click into a segment and see the composition of evidence that produced it. This is confirmed indirectly by the "asset-level decisions" pattern in predictive-maintenance dashboards, which separate portfolio-level prioritization from per-asset detail. Already covered as an Active requirement.

### Anti-Features (Commonly Requested, Often Problematic)

Cross-checked against PROJECT.md's existing Out of Scope list — all of PROJECT.md's stated exclusions are well-justified by domain research and are reaffirmed here, plus two additional anti-features the research surfaced that PROJECT.md doesn't explicitly name but should be aware of.

| Feature | Why Requested | Why Problematic | Alternative | PROJECT.md alignment |
|---------|---------------|------------------|-------------|------------------------|
| Deep-learning forecasting model at v1 | Seems more "cutting edge" / impressive than a trend baseline | No longitudinal dataset yet to train/validate against; unvalidatable complexity, classic overfitting/black-box risk that would undermine the explainability differentiator | Transparent trend-based baseline first, revisit once RoadObservation history accumulates | **Already excluded** — Out of Scope, correct |
| Treating raw YOLO confidence as ground truth / treating a single citizen report as a confirmed defect | Simpler to implement, tempting shortcut | Overstates certainty from one low-corroboration data point; predictive-maintenance research confirms mature platforms separate "model confidence" from "real-world certainty" via fused evidence scoring — skipping this undermines trust with road-authority users who will spot-check | Evidence fusion (already the plan) | **Already excluded** — Out of Scope, correct |
| Road-network-aware (true geometry) segmentation at v1 | Seems like "the right way" to do it | Requires road geometry data RoadTwin doesn't have yet; premature investment before the DBSCAN approach is validated | GPS/DBSCAN clustering v1, geometry-based segmentation later | **Already excluded** — Out of Scope, correct |
| Mandatory external inputs (traffic, weather, road classification, repair history) | These feel like they'd make scoring "more accurate" | Blocks the core pipeline from working without third-party data partnerships/integration work that may not materialize; research confirms PMS tools treat these as enhancement layers, not blockers | Enhancement-only inputs, added last | **Already excluded** — Out of Scope, correct |
| Presenting RHS/priority weights as scientifically validated | Feels more credible to say "our formula is proven" | Weights are placeholders; overclaiming validation risks credibility loss with technically sophisticated government buyers who will ask for methodology | Publish as placeholder/tunable, be explicit about pending calibration | **Already excluded** — Out of Scope, correct |
| Many disconnected AI bolt-on features (e.g., adding chatbots, generic image classifiers unrelated to the core pipeline) | Tempting to add "AI" wherever possible for perceived innovation | Fragments the value story; PROJECT.md's whole thesis is a single coherent fusion→segment→health→prediction→priority pipeline, and disconnected features dilute focus and add maintenance burden | Every new capability must plug into the existing pipeline | **Already excluded** — Out of Scope, correct |
| **[New from research]** Gamification (badges, leaderboards, points for reporting) | Seen in some crowdsourced civic apps (e.g., CityPulse-style apps use XP/leaderboards) to drive engagement | Risks incentivizing volume over quality — directly conflicts with RoadTwin's evidence-fusion philosophy, which deliberately weights corroboration/quality over raw report count; could invite gaming of the evidence score | Community upvote/verification (already planned) is sufficient engagement signal without incentivizing spam | Not in PROJECT.md; recommend explicitly excluding to protect evidence-score integrity |
| **[New from research]** Real-time/live-updating dashboard (sub-minute refresh, streaming architecture) | "Real-time everything" feels modern and matches consumer-app expectations | Road condition changes on the scale of days/weeks, not seconds; a streaming architecture adds significant infrastructure complexity (websockets, live pipelines) for a domain where near-real-time (periodic refresh, e.g. on new report ingestion) is functionally identical to true real-time from a road-authority's perspective | Standard request/response refresh on report submission or periodic batch recompute of health/priority scores | Not in PROJECT.md; recommend flagging so a future phase doesn't over-engineer this |

## Feature Dependencies

```
Citizen report submission (image+GPS+timestamp)
    └──requires──> Citizen identity (even lightweight/anonymous-device) [GAP — recommend adding]
                       └──enables──> Rate limiting per submitter [GAP — recommend adding]
                       └──enables──> Notification-on-status-change [GAP — recommend adding]

YOLOv8/RDD2022 detection persistence
    └──requires──> Report submission (image must exist first)

Observation-level severity (from bbox features)
    └──requires──> Detection persistence

DBSCAN duplicate/near-duplicate merge
    └──requires──> Report submission with GPS

Point observations → Road Segments (DBSCAN aggregation)
    └──requires──> Duplicate merge logic (same clustering mechanism, different aggregation level)

Evidence score
    └──requires──> Detection persistence (ML confidence)
    └──requires──> Duplicate merge (spatial agreement input)
    └──requires──> Community upvote/verification (community validation input)
    └──requires──> Citizen identity (to prevent one user inflating "community" signal) [GAP dependency]

RoadObservation longitudinal history
    └──requires──> Road Segments to exist
    └──requires──> Evidence score (each observation entry needs a trust weight)

Road Health Score (RHS)
    └──requires──> RoadObservation history
    └──requires──> Evidence score (feeds "evidence burden" component)

Deterioration rate
    └──requires──> RHS computed at 2+ points in time (requires accumulated history — cannot exist at cold-start)

30/60/90-day forecast baseline
    └──requires──> Deterioration rate
    └──requires──> Sufficient RHS history points to fit a trend line (cold-start problem: needs a minimum-data-points policy)

Maintenance priority score
    └──requires──> RHS, deterioration rate, evidence score, damage density (all upstream layers)
    └──enhances(optional)──> Traffic/road-importance/vulnerable-proximity/repair-recency (enhancement-only per Out of Scope)

Priority-score explainability ("why this road ranked where it did")
    └──requires──> Maintenance priority score (must exist to explain)

Authority dashboard (priority queue + road detail + explainability)
    └──requires──> Maintenance priority score + explainability
    └──requires──> Admin/staff authentication and roles [GAP — recommend adding as explicit requirement, not implicit]

Admin/repair workflow (status transitions)
    └──requires──> Admin/staff authentication and roles [GAP dependency]
    └──enhances──> Notification-on-status-change (citizen-facing loop-close) [GAP dependency]

Spam/abuse rate limiting ──conflicts-if-absent──> Evidence score integrity
    (unlimited unauthenticated submission volume can be gamed to inflate "observation count" and "community validation" inputs to evidence score)
```

### Dependency Notes

- **Evidence score requires citizen identity (even lightweight):** PROJECT.md's evidence score explicitly includes "observation count" and "community validation" as inputs. Without any way to distinguish unique submitters (even an anonymous device/session ID, not necessarily full accounts), the same person could submit the same report repeatedly or upvote their own report to inflate corroboration — directly undermining the evidence-fusion differentiator that is RoadTwin's core value proposition. This is the single most important gap to flag: it's not "nice to have," it's a precondition for the evidence score to mean what PROJECT.md claims it means.
- **Deterioration rate and forecast require a cold-start policy:** Both require 2+ RHS data points over time, but a freshly-onboarded road segment will have exactly one. The roadmap should account for a defined "insufficient data" state (e.g., show RHS but withhold deterioration/forecast until N observations exist) rather than silently producing a zero or misleading value.
- **Admin/staff auth enhances the admin/repair workflow and authority dashboard, which PROJECT.md already lists as Active requirements:** the dependency isn't optional — an "authority dashboard" that anyone can access without authentication is not viable for a government-facing product, even at MVP. This should be added explicitly rather than assumed implicit in "admin/repair workflow."
- **Spam/rate-limiting conflicts with evidence-score integrity if absent:** this is the clearest through-line from the research — every civic-reporting reference product treats rate limiting/duplicate detection as inseparable from data-quality assurance, and RoadTwin's evidence-fusion model is *more* exposed to this risk than a typical civic app because it explicitly weights corroboration as evidence of real-world certainty.
- **Priority score explainability enhances but does not replace the underlying score's correctness:** research on predictive-maintenance dashboards is clear that rationale/threshold explanations are expected *in addition to* the ranked score, not as a substitute for good weighting — this reinforces that PROJECT.md's "weights are placeholders" caveat should stay visible in the explainability UI itself (e.g., a visible "these weights are provisional" note), not just in internal documentation.

## MVP Definition

### Launch With (v1)

Everything already in PROJECT.md's Active list, plus the gaps below that are necessary for the Active list to actually function safely and credibly with real citizens and a real government buyer:

- [ ] All 16 Active requirements from PROJECT.md (report submission → detection persistence → clustering → segments → evidence score → RHS → deterioration → forecast baseline → priority score → explainability → public map → authority dashboard → admin workflow → data model)
- [ ] **[Recommended addition]** Lightweight citizen identity (anonymous device/session ID or simple email — full account system not required) — essential for evidence-score integrity and rate limiting, both of which PROJECT.md's Active requirements implicitly depend on
- [ ] **[Recommended addition]** Basic submission rate limiting (per device/IP/session) — essential table stakes confirmed across every civic-reporting reference product; prevents evidence-score gaming
- [ ] **[Recommended addition]** Admin/staff authentication with a single "authority staff" role — the authority dashboard and admin/repair workflow cannot be a credible government-facing feature without this; low complexity to add at v1, high complexity/risk to retrofit later
- [ ] **[Recommended addition]** Minimal automated status-change notification to the reporter (even just an in-app "your report's status changed" indicator, not necessarily email/SMS infra) — closes the trust loop that every 311/SeeClickFix-class reference product treats as core

### Add After Validation (v1.x)

- [ ] Flag-for-moderation path on individual reports (beyond automated evidence scoring) — add once real-world abuse patterns are observed, rather than speculatively building a full moderation queue before there's real abuse to moderate
- [ ] CSV/data export from the authority dashboard — add once a real government pilot user asks for it (common ask for council reporting/grant justification, but not blocking initial validation)
- [ ] Weight sensitivity/what-if view on the priority queue (adjust weighting, see rank shift live) — natural extension of the "weights are placeholders" transparency principle once the base explainability UI is proven out
- [ ] Email/SMS notification channel (vs. in-app only) — upgrade once there's a validated user base who wants it

### Future Consideration (v2+)

- [ ] Budget-constrained optimization ("given $X, which repair combination maximizes network health") — genuinely valuable per government-dashboard research, but requires the core ranked-queue-with-explainability to be validated first, and requires cost-per-repair data RoadTwin doesn't currently model
- [ ] True road-network-geometry-aware segmentation — already explicitly deferred in PROJECT.md Out of Scope, reaffirm here
- [ ] Deep-learning forecasting model — already explicitly deferred in PROJECT.md Out of Scope, reaffirm here
- [ ] Full account system with citizen report history/profile — only needed if gamification or personalized notification preferences become priorities, neither of which is core to RoadTwin's differentiator

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Report submission (image+GPS+timestamp) | HIGH | LOW | P1 |
| Per-detection persistence | HIGH | MEDIUM | P1 |
| DBSCAN duplicate merge / segment clustering | HIGH | MEDIUM | P1 |
| Evidence score | HIGH | MEDIUM-HIGH | P1 |
| Road Health Score | HIGH | MEDIUM | P1 |
| Deterioration rate | HIGH | LOW-MEDIUM | P1 |
| Trend-based forecast baseline | HIGH | MEDIUM | P1 |
| Maintenance priority score + explainability | HIGH | HIGH | P1 |
| Public map | HIGH | LOW-MEDIUM | P1 |
| Authority dashboard (queue, detail, explainability) | HIGH | HIGH | P1 |
| Admin/repair workflow (status transitions) | HIGH | LOW-MEDIUM | P1 |
| **Citizen lightweight identity** | HIGH (blocks evidence-score integrity) | LOW | **P1 — recommend elevating** |
| **Submission rate limiting** | HIGH (blocks abuse) | LOW | **P1 — recommend elevating** |
| **Admin/staff authentication + roles** | HIGH (blocks dashboard credibility) | LOW-MEDIUM | **P1 — recommend elevating** |
| **Status-change notification (in-app minimum)** | MEDIUM-HIGH (closes trust loop) | LOW | **P1/P2 — recommend at least in-app version at v1** |
| Manual moderation/flag path | MEDIUM | LOW-MEDIUM | P2 |
| CSV export | MEDIUM (high for government buyers specifically) | LOW | P2 |
| Weight sensitivity/what-if view | MEDIUM | MEDIUM | P2 |
| Budget-constrained optimization | MEDIUM-HIGH (long-term) | HIGH | P3 |
| Gamification | LOW (conflicts with evidence-score philosophy) | MEDIUM | Do not build (anti-feature) |
| True real-time streaming dashboard | LOW (over-engineering for this domain's update cadence) | HIGH | Do not build (anti-feature) |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | SeeClickFix / FixMyStreet (civic reporting) | StreetSaver / Cartegraph (PMS) | RoadBotics (AI road scoring) | RoadTwin's Approach |
|---------|----------------------------------------------|----------------------------------|-------------------------------|----------------------|
| Report intake | Citizen photo + description, no per-defect breakdown | Inspector-driven data collection (mobileRater), not crowdsourced | AI-scored from fleet-mounted smartphones, not crowdsourced | Citizen photo intake + per-detection AI persistence — combines crowdsourcing with per-defect granularity neither reference category does |
| Condition scoring | None (report status only, no condition score) | PCI 0-100, industry-standard, inspector/algorithm-calibrated | HD-PCI 0-100 + 1-5 per-10ft rating, AI-only | Road Health Score 0-100 with published interpretation bands, computed from fused citizen+AI evidence rather than either pure inspection or pure AI |
| Trust/evidence handling | Raw citizen report, upvotes as sole corroboration signal | Trained-inspector judgment (implicitly high trust, no formal "evidence score") | Model confidence only, no independent corroboration layer | Explicit multi-signal evidence fusion (ML confidence + spatial + temporal + community) — genuinely distinct from all three references |
| Trend/forecasting | None | Budget-scenario projected PCI (network-level, engineering decay curves) | None (point-in-time scoring only) | Per-segment 30/60/90-day transparent trend forecast — more granular than PMS budget scenarios, more forward-looking than RoadBotics |
| Prioritization | Implicit (most-upvoted/most-recent surfaces informally) | Budget-optimization-driven recommendation engine | Sortable by rating/distress density, no formal weighted priority score | Multi-factor priority score (8 inputs) with mandatory human-readable explanation — closest in spirit to PMS budget tools but with explicit per-item rationale, which neither PMS nor RoadBotics tooling emphasizes |
| Citizen-facing transparency | Public map + status tracking | Typically internal/staff-only, not citizen-facing | Typically internal/staff-only, not citizen-facing | Public map showing health/trends/damage clusters — RoadTwin is unusual in exposing the intelligence layer (not just raw reports) to citizens, not just staff |
| Auth/roles | Full citizen accounts + staff CRM roles (mature commercial product) | Staff-only, enterprise access control | Staff-only, enterprise access control | **Gap identified**: PROJECT.md does not yet explicitly specify citizen identity or staff roles — recommend adding per findings above |

## Sources

- [SeeClickFix — 311 Request and Work Management Software](https://seeclickfix.com/)
- [SeeClickFix (Wikipedia)](https://en.wikipedia.org/wiki/SeeClickFix)
- [SeeClickFix and Respect to FixMyStreet](https://gov.seeclickfix.com/2009/06/26/seeclickfix-and-respect-to-fixmystreet/)
- [Citizen Reporting Platforms Guide - Mark-a-Spot](https://www.mark-a-spot.com/citizen-reporting-platforms)
- [311 CRM Request Management Software for Government - CivicPlus](https://www.civicplus.com/seeclickfix-311-crm/)
- [StreetSaver Pavement Management Software | Cities & Counties](https://streetsaver.com/built-for/cities-and-counties/)
- [Pavement Management | StreetSaver](https://streetsaver.com/)
- [StreetSaver helps cities, counties get bigger returns on pavement investments](https://blog.bayareametro.gov/posts/streetsaverr-helps-cities-counties-get-bigger-returns-pavement-investments)
- [Pavement Condition Index (PCI) - ArcGIS](https://experience.arcgis.com/experience/be9e6f9d422645e18e73498f1f78fcc5)
- [RoadBotics Debuts HD PCI Ratings On Road Assessment Platform](https://informedinfrastructure.com/post/roadbotics-debuts-hd-pci-ratings-on-road-assessment-platform)
- [RoadBotics Now Offers Road Condition Scores Every 10 Feet - GovTech](https://www.govtech.com/biz/RoadBotics-Now-Offers-Road-Condition-Scores-Every-10-Feet.html)
- [RoadBotics Adds Pavement Distress Identification to Software - GovTech](https://www.govtech.com/biz/RoadBotics-Adds-Pavement-Distress-Identification-to-Software.html)
- [RoadBotics' AI Could Change the Way Cities Maintain Roads - IEEE Spectrum](https://spectrum.ieee.org/roadbotics-ai-could-change-the-way-cities-maintain-roads)
- [How AI Prioritizes Equipment Maintenance Using Asset Risk Scoring - Oxmaint](https://oxmaint.com/blog/post/use-ai-prioritize-equipment-maintenance)
- [Predictive Maintenance Decision Intelligence | BridgeOps AI](https://bridge-ops.ai/projects/predictive-maintenance-platform-v2/)
- [Top 10 Predictive Maintenance Platforms: Features, Pros, Cons & Comparison](https://www.rajeshkumar.xyz/blog/predictive-maintenance-platforms/)
- [Maintenance technologies for roads and its prioritization (ResearchGate)](https://www.researchgate.net/publication/364956294_Maintenance_technologies_for_roads_and_its_prioritization)
- [Prioritizing Road Maintenance on a Limited Budget - Oxmaint](https://oxmaint.com/industries/government/road-maintenance-prioritization-limited-budget-municipal)
- [Road Maintenance Prioritization (RMP) System - ISPRS Archives](https://isprs-archives.copernicus.org/articles/XLVIII-4-W18-2025/173/2026/isprs-archives-XLVIII-4-W18-2025-173-2026.pdf)
- [Evaluation of prioritization methods for effective pavement maintenance of urban roads - Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/10298436.2012.657798)
- [CityPulse gamified civic reporting app (GitHub)](https://github.com/mujahiddxd/citypulse-gamified-civic-reporting-app)
- [Citizen Reporting App: Empower Your Voice](https://citizenup.co/en/citizen-reporting-app-empower-your-voice/)
- [Power of the 311 Mobile App: Make City Living Easier](https://www.apps365.com/blog/the-power-of-311-mobile-app/)
- [311 CRM Request Management Software for Government - CivicPlus](https://www.civicplus.com/citizen-request-management/)
- [What is a 311 CRM System? - Gestisoft](https://www.gestisoft.com/en/blog/what-is-a-311-crm-system)
- [311 Request Management Software (Open311) - Mark-a-Spot](https://www.mark-a-spot.com/311-request-management)

---
*Feature research for: RoadTwin (predictive road-health & maintenance-intelligence system)*
*Researched: 2026-09-22*
