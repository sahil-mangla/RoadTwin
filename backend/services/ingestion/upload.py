"""Image upload validation and MinIO object storage (D-07, D-08, D-09).

Threats this module exists to close:
- T-02-02 (decompression bomb): the upload body is read with a hard byte
  cap before any Pillow decode, and Pillow's own decompression-bomb
  warning is promoted to a hard error.
- T-02-03 (client-supplied storage key): the MinIO object key is derived
  only from a server-generated Report UUID and a server-determined
  extension -- `upload.filename` is never read into it.
- T-02-06 (permanent public image URL): retrieval is only ever through a
  short-lived presigned URL, minted per request and never cached.
"""

from __future__ import annotations

import functools
import io
import uuid
import warnings
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile, status
from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageOps

from backend.core.config import settings

ALLOWED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG"})

# HEIC is deliberately excluded from the v1 allow-list: 02-RESEARCH.md's
# Open Question 2 flags that Pillow's stock build has no guaranteed
# libheif support. Plan 02-06 resolves this with a real test against the
# format allow-list rather than shipping a format that silently 422s
# every iPhone upload.
_FORMAT_TO_EXTENSION = {"JPEG": "jpg", "PNG": "png"}
_FORMAT_TO_CONTENT_TYPE = {"JPEG": "image/jpeg", "PNG": "image/png"}


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    pillow_format: str
    extension: str
    content_type: str


async def validate_and_normalize_image(upload: UploadFile) -> NormalizedImage:
    """Bounded-read, decoded, orientation-normalized, evidence-preserving upload.

    Reads at most `max_upload_bytes + 1` bytes -- never the stream
    unbounded followed by a length check after the fact, which is an
    unbounded-memory vector (T-02-02).
    """
    raw = await upload.read(settings.max_upload_bytes + 1)
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"image exceeds the {settings.max_upload_bytes}-byte upload limit",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(raw))
            img.verify()
    except Image.DecompressionBombError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="image rejected: declared pixel dimensions exceed the decompression-bomb guard",
        )
    except Image.DecompressionBombWarning:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="image rejected: declared pixel dimensions exceed the decompression-bomb guard",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="image could not be decoded",
        )

    # `verify()` leaves the Image instance unusable for further access, so
    # a fresh handle is opened for the format check and any transpose.
    img = Image.open(io.BytesIO(raw))
    if img.format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unsupported image format: {img.format!r}",
        )

    pillow_format = img.format
    extension = _FORMAT_TO_EXTENSION[pillow_format]
    content_type = _FORMAT_TO_CONTENT_TYPE[pillow_format]

    orientation = img.getexif().get(0x0112)
    if orientation is None or orientation == 1:
        # No rotation required -- return the original bytes untouched so
        # the stored evidence is byte-identical to what the citizen
        # uploaded (the evidence-integrity prohibition).
        return NormalizedImage(
            data=raw,
            pillow_format=pillow_format,
            extension=extension,
            content_type=content_type,
        )

    transposed = ImageOps.exif_transpose(img)
    buffer = io.BytesIO()
    if pillow_format == "JPEG":
        # `quality="keep"` reuses the original quantization tables, adding
        # no generation loss beyond the unavoidable rotation itself.
        transposed.save(buffer, format="JPEG", quality="keep")
    else:
        transposed.save(buffer, format=pillow_format)

    return NormalizedImage(
        data=buffer.getvalue(),
        pillow_format=pillow_format,
        extension=extension,
        content_type=content_type,
    )


def _dms_to_decimal(dms, ref: str) -> float:
    """Converts an EXIF GPS degrees/minutes/seconds rational triple to decimal degrees."""
    degrees, minutes, seconds = (float(v) for v in dms)
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


def extract_exif_gps(raw: bytes) -> tuple[float, float] | None:
    """Extracts a candidate (latitude, longitude) from EXIF GPS tags, or None.

    Uses Pillow's built-in EXIF access (`getexif().get_ifd(GPSInfo)`) rather
    than a separate third-party EXIF-parsing package: 02-RESEARCH.md's
    Alternatives-Considered table sanctions this path, and that other
    candidate was the one dependency whose upstream repository the
    legitimacy checker could not confirm -- avoiding it removes both a
    dependency and a supply-chain checkpoint.

    Returns `None` for every degenerate case (no EXIF, no GPSInfo IFD,
    malformed/zero-denominator rationals, an out-of-range result, or any
    other decode exception) rather than raising -- a photo with stripped or
    absent GPS metadata is the ordinary case (phone camera apps and OS
    privacy settings routinely remove it), not an error condition
    (02-RESEARCH.md Pitfall 5).

    This is a CANDIDATE pin position only -- see this module's callers
    (backend/routes/reports.py's `probe_image_exif_gps`) for the D-10
    contract that the result must pass through citizen map confirmation
    before it can ever reach a submitted Report.
    """
    from PIL import ExifTags

    try:
        img = Image.open(io.BytesIO(raw))
        exif = img.getexif()
        gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
        if not gps_ifd:
            return None

        lat_dms = gps_ifd.get(2)  # GPSLatitude
        lat_ref = gps_ifd.get(1)  # GPSLatitudeRef
        lng_dms = gps_ifd.get(4)  # GPSLongitude
        lng_ref = gps_ifd.get(3)  # GPSLongitudeRef
        if not lat_dms or not lng_dms or not lat_ref or not lng_ref:
            return None

        latitude = _dms_to_decimal(lat_dms, lat_ref)
        longitude = _dms_to_decimal(lng_dms, lng_ref)
    except Exception:
        return None

    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None

    return latitude, longitude


def generate_object_key(report_id: uuid.UUID, extension: str) -> str:
    """Derives the MinIO object key only from a server-generated id (D-08, T-02-03)."""
    return f"reports/{report_id}.{extension}"


@functools.lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    """Memoized so importing this module opens no network connection."""
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def put_report_image(object_key: str, image: NormalizedImage) -> None:
    """Writes the object, refusing to overwrite an existing key (evidence integrity)."""
    client = get_minio_client()
    try:
        client.stat_object(settings.minio_bucket, object_key)
    except S3Error as exc:
        if exc.code not in ("NoSuchKey", "NoSuchObject"):
            raise
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an object already exists at this key",
        )

    client.put_object(
        settings.minio_bucket,
        object_key,
        io.BytesIO(image.data),
        length=len(image.data),
        content_type=image.content_type,
    )


def get_presigned_image_url(object_key: str) -> str:
    """Mints a fresh presigned GET URL. Never cache or persist it (D-09, T-02-06)."""
    import datetime as dt

    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=dt.timedelta(seconds=settings.minio_presigned_url_ttl_seconds),
    )


def get_report_image_bytes(object_key: str) -> bytes:
    """Reads a stored report image back out of MinIO (used by the perception worker)."""
    client = get_minio_client()
    response = client.get_object(settings.minio_bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
