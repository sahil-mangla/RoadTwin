"""RoadTwin FastAPI application entrypoint.

Run with `uvicorn backend.main:app` from the repository root.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="RoadTwin API", version="0.1.0")

# Permissive CORS for the two localhost Vite dev-server origins only, so
# Plan 03's frontend can call the API directly if its dev-server proxy is
# bypassed. Not a production CORS policy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Mounted only when settings.skeleton_routes_enabled is true (threat
# T-01-07) -- these routes are unauthenticated and prove wiring only, not
# a production ingestion path. See backend/routes/skeleton.py's module
# docstring and 01-SKELETON.md's "Skeleton Retirement Criteria".
if settings.skeleton_routes_enabled:
    from backend.routes import skeleton

    app.include_router(skeleton.router)
    logger.warning(
        "Skeleton routes (/api/skeleton/*) are mounted -- unauthenticated, "
        "for local development only. Set SKELETON_ROUTES_ENABLED=false "
        "outside local dev."
    )

# The real citizen ingestion API (INGT-01..04, Phase 2) -- mounted
# unconditionally, unlike the diagnostic skeleton router above.
from backend.routes import reports  # noqa: E402

app.include_router(reports.router)

try:
    from backend.services.ingestion.upload import ensure_bucket

    ensure_bucket()
except Exception:
    # A MinIO outage must not prevent the app (or test collection, which
    # imports backend.main) from starting (T-02-11).
    logger.error("Could not reach the docker-compose minio service at startup")
