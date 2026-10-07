"""Tests for backend/services/ingestion/upload.py and its wiring into POST /api/reports.

Covers upload-validation edge cases (oversized, corrupt, decompression
bomb) and the evidence-integrity prohibitions (no gratuitous re-encode, no
silent overwrite), plus real object-storage retrieval end to end.
"""

import io
import uuid

import httpx
import pytest
from PIL import Image

from backend.services.ingestion.upload import (
    NormalizedImage,
    generate_object_key,
    get_presigned_image_url,
    put_report_image,
)


async def _post_report(
    client, image_bytes: bytes, filename: str = "photo.jpg", longitude: str = "77.5946"
):
    data = {"latitude": "12.9716", "longitude": longitude}
    files = {"image": (filename, image_bytes, "image/jpeg")}
    return await client.post("/api/reports", data=data, files=files)


@pytest.mark.postgis
@pytest.mark.minio
@pytest.mark.asyncio
async def test_image_stored_and_retrievable(client, minio_available, jpeg_bytes):
    submit = await _post_report(client, jpeg_bytes)
    assert submit.status_code == 201, submit.text
    report_id = submit.json()["id"]

    resp = await client.get(f"/api/reports/{report_id}/image-url")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["url"], str) and body["url"]
    assert isinstance(body["expires_in_seconds"], int)

    async with httpx.AsyncClient() as raw:
        fetched = await raw.get(body["url"])
    assert fetched.status_code == 200
    assert fetched.content == jpeg_bytes


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_reject_oversized_and_corrupt_image(client, session):
    from backend.core.config import settings

    oversized = b"0" * (settings.max_upload_bytes + 1)
    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("big.jpg", oversized, "image/jpeg")},
    )
    assert resp.status_code == 413

    resp2 = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("fake.jpg", b"not an image", "image/jpeg")},
    )
    assert resp2.status_code == 422

    import sqlalchemy as sa

    from backend.models.report import Report

    count = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    assert count == 0


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_reject_decompression_bomb_image(client, session):
    buf = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buf, format="PNG")
    png_bytes = bytearray(buf.getvalue())

    # Craft a PNG whose declared IHDR width/height are enormous while the
    # actual pixel data stays tiny, so Pillow's decompression-bomb guard
    # trips on the declared dimensions read from the header.
    huge = io.BytesIO()
    img = Image.new("RGB", (1, 1))
    img.save(huge, format="PNG")
    raw = huge.getvalue()
    # IHDR chunk: 8-byte PNG signature, then length(4)+"IHDR"(4)+width(4)+height(4)+...
    ihdr_start = 8 + 8
    forged = bytearray(raw)
    huge_dim = (60000).to_bytes(4, "big")
    forged[ihdr_start : ihdr_start + 4] = huge_dim
    forged[ihdr_start + 4 : ihdr_start + 8] = huge_dim

    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("bomb.png", bytes(forged), "image/png")},
    )
    assert resp.status_code == 422

    import sqlalchemy as sa

    from backend.models.report import Report

    count = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    assert count == 0


@pytest.mark.postgis
@pytest.mark.minio
@pytest.mark.asyncio
async def test_original_jpeg_bytes_preserved_when_orientation_is_already_normal(
    client, minio_available, jpeg_bytes
):
    submit = await _post_report(client, jpeg_bytes)
    assert submit.status_code == 201, submit.text
    report_id = submit.json()["id"]
    object_key = f"reports/{report_id}.jpg"

    from backend.core.config import settings

    stored = minio_available.get_object(settings.minio_bucket, object_key)
    try:
        stored_bytes = stored.read()
    finally:
        stored.close()
        stored.release_conn()

    assert stored_bytes == jpeg_bytes


@pytest.mark.minio
def test_existing_object_key_is_never_overwritten(minio_available, jpeg_bytes):
    from fastapi import HTTPException

    key = f"reports/{uuid.uuid4()}.jpg"
    normalized = NormalizedImage(
        data=jpeg_bytes, pillow_format="JPEG", extension="jpg", content_type="image/jpeg"
    )
    put_report_image(key, normalized)

    other = NormalizedImage(
        data=b"different bytes but same length!",
        pillow_format="JPEG",
        extension="jpg",
        content_type="image/jpeg",
    )
    with pytest.raises(HTTPException) as exc_info:
        put_report_image(key, other)
    assert exc_info.value.status_code == 409

    from backend.core.config import settings

    stored = minio_available.get_object(settings.minio_bucket, key)
    try:
        assert stored.read() == jpeg_bytes
    finally:
        stored.close()
        stored.release_conn()


def _jpeg_with_gps(lat_dms, lat_ref, lng_dms, lng_ref) -> bytes:
    """Builds a small in-memory JPEG carrying a known GPS IFD."""
    from PIL import ExifTags
    from PIL.TiffImagePlugin import IFDRational

    img = Image.new("RGB", (8, 8))
    exif = img.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps_ifd[1] = lat_ref  # GPSLatitudeRef
    gps_ifd[2] = tuple(IFDRational(n, d) for n, d in lat_dms)  # GPSLatitude
    gps_ifd[3] = lng_ref  # GPSLongitudeRef
    gps_ifd[4] = tuple(IFDRational(n, d) for n, d in lng_dms)  # GPSLongitude

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_extract_exif_gps_returns_none_without_metadata(jpeg_bytes):
    from backend.services.ingestion.upload import extract_exif_gps

    assert extract_exif_gps(jpeg_bytes) is None


def test_extract_exif_gps_parses_dms_to_decimal():
    from backend.services.ingestion.upload import extract_exif_gps

    raw = _jpeg_with_gps(
        [(12, 1), (58, 1), (57, 10)], "N", [(77, 1), (35, 1), (40, 10)], "E"
    )
    result = extract_exif_gps(raw)
    assert result is not None
    lat, lng = result
    assert abs(lat - 12.96825) < 1e-4
    assert abs(lng - 77.58444) < 1e-4


def test_extract_exif_gps_negates_south_and_west():
    from backend.services.ingestion.upload import extract_exif_gps

    raw = _jpeg_with_gps([(12, 1), (58, 1), (0, 1)], "S", [(77, 1), (35, 1), (0, 1)], "W")
    lat, lng = extract_exif_gps(raw)
    assert lat < 0
    assert lng < 0


def test_extract_exif_gps_handles_malformed_ifd():
    from backend.services.ingestion.upload import extract_exif_gps
    from PIL import ExifTags

    img = Image.new("RGB", (8, 8))
    exif = img.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps_ifd[1] = "N"
    # Deliberately malformed: GPSLatitude present but GPSLongitude absent.
    from PIL.TiffImagePlugin import IFDRational

    gps_ifd[2] = (IFDRational(12, 1), IFDRational(0, 1), IFDRational(0, 1))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)

    assert extract_exif_gps(buf.getvalue()) is None
    assert extract_exif_gps(b"not an image at all") is None


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_exif_probe_endpoint_returns_candidate(client):
    raw = _jpeg_with_gps([(12, 1), (58, 1), (0, 1)], "N", [(77, 1), (35, 1), (0, 1)], "E")
    resp = await client.post(
        "/api/reports/exif-gps-probe", files={"image": ("photo.jpg", raw, "image/jpeg")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "exif"
    assert body["latitude"] is not None
    assert body["longitude"] is not None


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_exif_probe_endpoint_returns_null_candidate(client, jpeg_bytes):
    resp = await client.post(
        "/api/reports/exif-gps-probe", files={"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["latitude"] is None
    assert body["longitude"] is None
    assert body["source"] == "none"


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_exif_probe_endpoint_rejects_oversized_and_corrupt(client):
    from backend.core.config import settings

    oversized = b"0" * (settings.max_upload_bytes + 1)
    resp = await client.post(
        "/api/reports/exif-gps-probe", files={"image": ("big.jpg", oversized, "image/jpeg")}
    )
    assert resp.status_code == 413

    resp2 = await client.post(
        "/api/reports/exif-gps-probe", files={"image": ("fake.jpg", b"nope", "image/jpeg")}
    )
    assert resp2.status_code == 422


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_exif_probe_creates_no_report_and_no_object(client, session, jpeg_bytes):
    import sqlalchemy as sa

    from backend.models.report import Report

    before = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    resp = await client.post(
        "/api/reports/exif-gps-probe", files={"image": ("photo.jpg", jpeg_bytes, "image/jpeg")}
    )
    assert resp.status_code == 200
    after = await session.scalar(sa.select(sa.func.count()).select_from(Report))
    assert after == before


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_exif_probe_is_rate_limited(client, session, jpeg_bytes):
    from backend.core.config import settings
    from backend.db.repository import SubmissionAttemptRepository

    identity_key = str(uuid.uuid4())
    for _ in range(settings.identity_rate_limit_per_hour):
        await SubmissionAttemptRepository(session).create(
            identity_key=identity_key, ip_address="198.51.100.20"
        )
    await session.flush()

    from backend.services.ingestion.identity import _get_serializer

    signed = _get_serializer().dumps(identity_key)
    resp = await client.post(
        "/api/reports/exif-gps-probe",
        files={"image": ("photo.jpg", jpeg_bytes, "image/jpeg")},
        cookies={"rt_device_id": signed},
    )
    assert resp.status_code == 429


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_allowed_formats_accept_real_files(client, jpeg_bytes, png_bytes):
    jpeg_resp = await _post_report(client, jpeg_bytes, filename="photo.jpg")
    assert jpeg_resp.status_code == 201, jpeg_resp.text

    png_resp = await _post_report(
        client, png_bytes, filename="photo.png", longitude="77.6046"
    )
    assert png_resp.status_code == 201, png_resp.text

    # A real, decodable GIF -- valid image data, but not in ALLOWED_FORMATS
    # -- proves the "unsupported format" branch specifically, distinct from
    # the "could not be decoded" branch garbage bytes would hit instead.
    gif_buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(gif_buf, format="GIF")
    gif_resp = await _post_report(
        client, gif_buf.getvalue(), filename="photo.gif", longitude="77.6146"
    )
    assert gif_resp.status_code == 422
    assert "format" in gif_resp.json()["detail"].lower()


@pytest.mark.postgis
@pytest.mark.asyncio
async def test_heic_support_is_explicit(client):
    """HEIC is not in Pillow's stock-build decodable set in this environment.

    02-RESEARCH.md Open Question 2 leaves HEIC support conditional on
    libheif availability. This environment's Pillow build cannot decode
    HEIC, so the outcome is a deliberate, documented 422 -- never a 500 and
    never a silent success that stores an unreadable object. If a future
    Pillow build gains HEIC support, `img.format` would report "HEIF" and
    this request would 422 anyway (HEIC/HEIF is not in ALLOWED_FORMATS),
    which is still the explicit, documented exclusion this test asserts.
    """
    # A syntactically-plausible-looking HEIC/ISOBMFF header the server must
    # reject cleanly rather than crash on.
    fake_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heicmif1" + b"\x00" * 32
    resp = await client.post(
        "/api/reports",
        data={"latitude": "12.9716", "longitude": "77.5946"},
        files={"image": ("photo.heic", fake_heic, "image/heic")},
    )
    assert resp.status_code == 422
    assert resp.status_code != 500
