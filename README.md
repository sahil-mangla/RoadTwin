# RoadTwin

RoadTwin is a predictive road-health and maintenance-intelligence system.
Citizens submit geotagged photos of road damage; a YOLOv8/RDD2022
perception layer detects the damage, and RoadTwin fuses those observations
over time into per-road-segment health profiles — tracking condition,
deterioration rate, and future risk — to produce an explainable, ranked
maintenance queue for road authorities.

## Prerequisites

- Docker (for the PostgreSQL + PostGIS service)
- Python 3.12+
- Node 20+

## Run the full stack locally

1. `docker compose up -d postgres`
2. `pip install -r backend/requirements-dev.txt`
3. `alembic -c backend/alembic.ini upgrade head`
4. In two parallel terminals:
   - `uvicorn backend.main:app --reload --port 8000`
   - `npm --prefix frontend install && npm --prefix frontend run dev`

Then open http://localhost:5173.

## Run the tests

```
pytest backend/tests/ -v
```

## Project status

Phase 1 ships a **Walking Skeleton** only — the seven-entity data contract
(Report, Detection, RoadSegment, RoadObservation, RoadHealth, Prediction,
MaintenanceRecommendation) is locked and proven reachable end-to-end
(browser → FastAPI → Postgres/PostGIS → browser) through a minimal skeleton
page and API. No perception, clustering, evidence fusion, health scoring,
forecasting, or priority scoring exists yet. See
`.planning/phases/01-schema-core-data-contracts/01-SKELETON.md` for what is
deliberately out of scope in this phase.
