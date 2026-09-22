"""The single place coordinates become PostGIS geometry (01-RESEARCH.md Pitfall 1).

WKT/PostGIS point ordering is (longitude, latitude) -- the opposite of the
conversational "lat/lng" convention used by the browser Geolocation API and
almost every non-GIS API. Getting this backwards silently stores a
plausible-looking but geographically wrong point (often landing in the
ocean or a different continent, since both magnitudes look like valid
coordinates). Centralizing construction here means no other call site in
the codebase ever orders axes by hand.

Neither helper accepts an SRID argument -- SRID 4326 (WGS84) is hard-coded,
so an external caller can never choose one (threat T-01-02).
"""

from geoalchemy2 import WKTElement

_SRID = 4326


def make_point(latitude: float, longitude: float) -> WKTElement:
    """Builds a SRID-4326 POINT, correctly ordered (longitude, latitude)."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=_SRID)


def make_linestring(
    start_lat: float, start_lng: float, end_lat: float, end_lng: float
) -> WKTElement:
    """Builds a SRID-4326 two-vertex LINESTRING, ordered (longitude, latitude)."""
    return WKTElement(
        f"LINESTRING({start_lng} {start_lat}, {end_lng} {end_lat})", srid=_SRID
    )
