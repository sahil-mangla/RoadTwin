"""The real citizen ingestion API (INGT-01..04).

Prefix is `/api/reports`, not the bare `/reports` 02-RESEARCH.md/
ARCHITECTURE.md suggest: `frontend/vite.config.ts` proxies only `/api` to
the backend, so a `/reports` prefix would 404 in the browser dev flow.
`backend/routes/skeleton.py` stays untouched (D-12) -- this is a sibling
router, not a replacement.

Behind a reverse proxy, `request.client.host` is the proxy's own address
unless a trusted-proxy header policy is configured. The client-IP-derived
forwarded-address header some proxies set is deliberately NOT parsed
anywhere in this module: without a trusted-proxy allowlist, doing so would
let any caller assert an arbitrary source IP and reset their own rate-limit
counter (T-02-17).
"""

import datetime as dt
import uuid

import pydantic
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from minio.error import S3Error
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.db.repository import ReportRepository
from backend.db.session import get_session
from backend.schemas.report import ExifGpsCandidate, ReportCreate, ReportImageUrl, ReportRead
from backend.services.ingestion.identity import get_device_identity
from backend.services.ingestion.rate_limit import enforce_rate_limits, record_submission_attempt
from backend.services.ingestion.upload import (
    extract_exif_gps,
    generate_object_key,
    get_presigned_image_url,
    put_report_image,
    validate_and_normalize_image,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/exif-gps-probe", response_model=ExifGpsCandidate)
async def probe_image_exif_gps(
    request: Request,
    image: UploadFile,
    device_id: str = Depends(get_device_identity),
    session: AsyncSession = Depends(get_session),
) -> ExifGpsCandidate:
    """Offers a photo's EXIF GPS as a CANDIDATE pin for the confirmation UI.

    D-10 contract: the coordinates this endpoint returns are a candidate
    pin position for the frontend's map-confirmation step ONLY. Nothing in
    this backend may treat them as a submitted location -- `submit_report`
    below continues to accept latitude/longitude solely as explicit form
    fields the citizen confirmed on the map. This endpoint writes no
    Report row, no MinIO object and no SubmissionAttempt row: a probe is
    not a submission, and counting it as one would consume the citizen's
    submission quota before they ever press submit.

    Applies the identical size/format/bomb validation `submit_report` uses
    (T-02-25) and is rate-limited the same way (identity + IP counters
    only -- no coordinates are known yet, so the GPS cooldown is skipped)
    so this cannot become an unmetered image-processing side door.
    """
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limits(
        session, identity_key=device_id, ip_address=client_ip, latitude=None, longitude=None
    )

    normalized = await validate_and_normalize_image(image)
    candidate = extract_exif_gps(normalized.data)
    if candidate is None:
        return ExifGpsCandidate(latitude=None, longitude=None, source="none")
    latitude, longitude = candidate
    return ExifGpsCandidate(latitude=latitude, longitude=longitude, source="exif")


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def submit_report(
    request: Request,
    image: UploadFile,
    latitude: float = Form(...),
    longitude: float = Form(...),
    gps_accuracy_meters: float | None = Form(default=None),
    description: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    device_id: str = Depends(get_device_identity),
) -> ReportRead:
    # (1) Validate coordinates FIRST, via Pydantic, before any image byte
    # is read -- this is what keeps an invalid-GPS submission from ever
    # creating an orphan MinIO object.
    try:
        payload = ReportCreate(
            latitude=latitude,
            longitude=longitude,
            gps_accuracy_meters=gps_accuracy_meters,
            description=description,
        )
    except pydantic.ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    # No forwarded-header parsing -- see the module docstring (T-02-17).
    client_ip = request.client.host if request.client else "unknown"

    # Three cheap indexed Postgres reads reject a flood before the server
    # consumes the (potentially large) upload body below -- this gate sits
    # after the Pydantic validation above because the GPS cooldown needs
    # validated coordinates, and before the image is read for the reason
    # stated at the next step.
    await enforce_rate_limits(
        session,
        identity_key=device_id,
        ip_address=client_ip,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )

    # (2) Decode, bomb-guard and orientation-normalize the upload.
    normalized = await validate_and_normalize_image(image)

    # (3) The object key is derived only from a server-generated id.
    report_id = uuid.uuid4()
    object_key = generate_object_key(report_id, normalized.extension)

    # (4) Write to MinIO BEFORE the row insert: if the object write
    # succeeds and the insert then fails, the result is an orphaned
    # object with no referrer (harmless and prunable). The reverse order
    # can leave a committed Report row whose image_path points at an
    # object that was never stored, breaking INGT-04's "retrievable from
    # object storage via a reference on the Report record" invariant.
    try:
        put_report_image(object_key, normalized)
    except HTTPException:
        raise
    except S3Error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="object storage is unavailable",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="object storage is unavailable",
        )

    # (5) Let ReportRepository.create derive the PostGIS `location` column.
    report = await ReportRepository(session).create(
        id=report_id,
        image_path=object_key,
        timestamp=dt.datetime.now(dt.timezone.utc),
        submitter_identity_key=device_id,
        **payload.model_dump(exclude={"image_path", "timestamp"}),
    )

    # Written after the Report insert (not before) so the rollback
    # ordering holds: `get_session` commits both writes on clean exit and
    # rolls back both on any exception, so a failed Report insert never
    # consumes a rate-limit slot, and a 429'd request (which raises before
    # reaching here) never records an attempt at all.
    await record_submission_attempt(session, identity_key=device_id, ip_address=client_ip)

    return ReportRead.model_validate(report)


@router.get("/{report_id}/image-url", response_model=ReportImageUrl)
async def get_report_image_url(
    report_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ReportImageUrl:
    report = await ReportRepository(session).get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    if report.image_path is None:
        raise HTTPException(status_code=404, detail="report has no stored image")

    # Minted on every request and never stored on the Report row or cached
    # in the response model (D-09, T-02-06).
    return ReportImageUrl(
        url=get_presigned_image_url(report.image_path),
        expires_in_seconds=settings.minio_presigned_url_ttl_seconds,
    )
