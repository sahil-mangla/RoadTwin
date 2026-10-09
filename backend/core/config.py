"""Typed application settings.

Two separate database URLs are mandatory (01-RESEARCH.md Pitfall 3):
`asyncpg` drives the FastAPI app's async engine; `psycopg` (sync) drives
Alembic, which cannot run migrations through an async-only driver.

Phase 2 (INGT-01..04) extends this single class with every MinIO,
device-identity-cookie, rate-limit and upload-validation knob the
ingestion path needs (D-13: one flat Settings class, no second config
module). Every numeric value below is a CONTEXT.md Claude's-Discretion
resolution, made an environment-tunable Settings field rather than a
module constant so retuning it after launch needs no schema change:

- `identity_rate_limit_per_hour=10` / `ip_rate_limit_per_hour=20` and
  `gps_cooldown_meters=15.0` / `gps_cooldown_seconds=300` are
  02-RESEARCH.md Pattern 2's proposed defaults, sized deliberately
  small-radius/short-window (Pitfall 3) so the identity-agnostic cooldown
  catches an obvious spam burst without plausibly blocking a second real
  citizen photographing the same pothole minutes later.
- `max_upload_bytes=10485760` (10 MB) is the upload cap.
- `gps_imprecise_threshold_meters=50.0` is the non-blocking "location may
  be imprecise" hint threshold from D-11.
"""

import logging
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://roadtwin:roadtwin_dev@localhost:5432/roadtwin"
    database_url_sync: str = "postgresql+psycopg://roadtwin:roadtwin_dev@localhost:5432/roadtwin"
    skeleton_routes_enabled: bool = True

    # -- MinIO object storage (INGT-04) --
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "roadtwin"
    minio_secret_key: str = "roadtwin_dev_secret"
    minio_secure: bool = False
    minio_bucket: str = "roadtwin-reports"
    minio_presigned_url_ttl_seconds: int = 900

    # -- Device identity cookie (INGT-02, D-01/D-02) --
    device_id_cookie_name: str = "rt_device_id"
    device_id_cookie_max_age_seconds: int = 31536000
    device_id_cookie_secure: bool = False
    # No literal default (threat T-02-07): a hardcoded or shared signing
    # secret would let anyone forge a signed device identity. `str | None`
    # rather than a required `str` is deliberate -- a required field would
    # make `Settings()` raise at import time and break every Phase 1 test
    # that imports this module. See `resolve_device_id_cookie_secret()`.
    device_id_cookie_secret: str | None = None

    # -- Rate limiting & GPS cooldown (INGT-03, D-03..D-06) --
    identity_rate_limit_per_hour: int = 10
    ip_rate_limit_per_hour: int = 20
    rate_limit_window_seconds: int = 3600
    gps_cooldown_meters: float = 15.0
    gps_cooldown_seconds: int = 300
    submission_attempt_retention_days: int = 7

    # -- Upload validation (INGT-04, D-11) --
    max_upload_bytes: int = 10485760
    gps_imprecise_threshold_meters: float = 50.0

    # -- Async perception pipeline (PERC-01..03) --
    redis_url: str = "redis://localhost:6379"
    # Path to YOLOv8 weights trained on RDD2022. Unset means the worker
    # fails fast at startup rather than silently running a COCO model.
    yolo_weights_path: str | None = None
    yolo_conf_threshold: float = 0.25
    yolo_image_size: int = 640
    perception_job_max_tries: int = 3
    # Same-class boxes overlapping at least this much are one defect.
    detection_merge_iou: float = 0.5
    detection_merge_containment: float = 0.8
    # Delay before the first attempt so the submitting request's
    # transaction has committed by the time the worker looks the row up.
    perception_enqueue_delay_seconds: int = 2

    # -- Spatial clustering & segments (SPAT-01..03) --
    # Reports closer than this are treated as the same physical damage.
    duplicate_radius_meters: float = 15.0
    # Canonical points closer than this chain into one road segment.
    segment_cluster_radius_meters: float = 50.0
    # An unclaimed existing segment this close to a brand-new cluster is
    # re-used instead of minting a new identity.
    segment_reconcile_distance_meters: float = 50.0
    segmentation_defer_seconds: int = 30

    # -- Evidence fusion (EVID-01..04) --
    # Relative weights; scores are divided by their sum, so these only need
    # to be proportional. YOLO confidence is one input among five and, on
    # its own, can never lift an observation to full evidence.
    evidence_weight_ml_confidence: float = 0.35
    evidence_weight_observation_count: float = 0.20
    evidence_weight_spatial_agreement: float = 0.15
    evidence_weight_temporal_consistency: float = 0.15
    evidence_weight_community_validation: float = 0.15
    # Saturation points: the value at which a component reaches 1.0.
    evidence_count_saturation: int = 4          # independent reporters
    evidence_temporal_saturation_days: float = 7.0
    evidence_community_saturation: int = 3      # distinct corroborating voters
    # Status lifecycle thresholds (SCHM-03).
    evidence_confirmed_threshold: float = 0.70
    corroborated_min_independent_reporters: int = 2
    corroborated_min_votes: int = 2
    # A new snapshot is appended only when the score moved at least this much.
    evidence_resnapshot_delta: float = 0.10
    corroboration_ip_limit_per_hour: int = 30

    # -- Road health, deterioration & forecast (HLTH-02..04, FCST-01..03) --
    # PROVISIONAL starting values -- tunable, not validated. Health =
    # 100 - sum(weight * burden); weights are used as given (keep sum = 1).
    health_weight_severity: float = 0.50
    health_weight_density: float = 0.20
    health_weight_temporal: float = 0.20
    health_weight_evidence: float = 0.10
    # Evidence-weighted severity points at which the severity burden is 100.
    health_severity_saturation: float = 3.0
    # Evidence-weighted damages per 100 m at which the density burden is 100.
    health_density_saturation_per_100m: float = 5.0
    health_density_min_length_meters: float = 50.0
    # Damage first seen within this window counts as "recent deterioration".
    health_temporal_window_days: float = 30.0
    health_temporal_saturation: float = 3.0
    # A new RoadHealth row is appended when the score moved by at least
    # `health_resnapshot_delta` points or the last row is older than the
    # interval (so a stable road still builds a flat, informative history).
    health_snapshot_interval_hours: float = 24.0
    health_resnapshot_delta: float = 2.0
    # Minimum-data gate shared by the deterioration rate and the forecast.
    history_min_observation_reports: int = 3
    history_min_points: int = 4
    history_min_days: float = 14.0
    history_window_days: float = 180.0
    # Deterioration labels, in health points per day.
    deterioration_rapid_per_day: float = -0.5
    deterioration_slow_per_day: float = -0.1
    # Forecast: linear OLS below this many points, damped Holt from here up.
    forecast_holt_min_points: int = 5
    forecast_failure_health_threshold: float = 40.0
    forecast_accuracy_tolerance_days: float = 7.0

    model_config = SettingsConfigDict(
        env_file="backend/.env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()


def resolve_device_id_cookie_secret() -> str:
    """Returns the configured cookie-signing secret, or mints an ephemeral one.

    When `DEVICE_ID_COOKIE_SECRET` is unset, a per-process secret is minted
    with `secrets.token_urlsafe(32)` and a loud warning is emitted, per
    02-RESEARCH.md Pitfall 4: a signing secret with a public/shared default
    provides zero security. The consequence -- every process restart
    invalidates every outstanding cookie and therefore every device
    identity -- is accepted, loud-failure behaviour, not a bug.
    """
    if settings.device_id_cookie_secret:
        return settings.device_id_cookie_secret
    logger.warning(
        "DEVICE_ID_COOKIE_SECRET is not set -- minting an ephemeral "
        "per-process signing secret. Device identities will NOT survive "
        "a process restart. Set DEVICE_ID_COOKIE_SECRET in backend/.env "
        "outside local dev."
    )
    return secrets.token_urlsafe(32)
