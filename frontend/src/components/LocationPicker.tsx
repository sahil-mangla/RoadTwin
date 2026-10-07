import { useEffect, useMemo, useRef } from "react";
import type { Marker as LeafletMarker } from "leaflet";
import L from "leaflet";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";

// Without this, Leaflet resolves its default marker icon paths relative to
// the CSS, which breaks under Vite's asset hashing and yields an invisible
// marker -- a missing pin is exactly the failure that would make D-10's
// map-confirmation step impossible.
import "leaflet/dist/leaflet.css";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

L.Icon.Default.mergeOptions({
  iconUrl: markerIcon,
  iconRetinaUrl: markerIcon2x,
  shadowUrl: markerShadow,
});

export interface LatLngLiteral {
  lat: number;
  lng: number;
}

// Bengaluru coordinates, matching Phase 1's SkeletonPage.tsx pre-fill, so
// the deployment region is consistent across both pages.
export const DEFAULT_CENTER: LatLngLiteral = { lat: 12.9716, lng: 77.5946 };
export const DEFAULT_ZOOM = 16;

interface ClickToMoveProps {
  onMove: (pos: LatLngLiteral) => void;
}

function ClickToMove({ onMove }: ClickToMoveProps) {
  useMapEvents({
    click(e) {
      onMove({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

export interface LocationPickerProps {
  position: LatLngLiteral | null;
  accuracyMeters: number | null;
  onPositionChange: (pos: LatLngLiteral) => void;
  onGeolocationResult: (pos: LatLngLiteral, accuracyMeters: number | null) => void;
}

/**
 * Renders a Leaflet map with a draggable pin for the citizen to confirm or
 * move. Holds NO copy of the confirmed position itself -- `ReportSubmitPage`
 * owns the draft that actually gets submitted, so there is only ever one
 * source of truth for what a citizen is about to send.
 *
 * On mount, attempts browser geolocation once. Success only offers a
 * CANDIDATE pin via `onGeolocationResult` -- it is never treated as
 * confirmed. Denial or absence of the API leaves the map at
 * `DEFAULT_CENTER` for manual placement (D-10's failure path).
 */
export function LocationPicker({
  position,
  accuracyMeters,
  onPositionChange,
  onGeolocationResult,
}: LocationPickerProps) {
  const markerRef = useRef<LeafletMarker>(null);

  useEffect(() => {
    if (!navigator.geolocation) {
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        onGeolocationResult(
          { lat: pos.coords.latitude, lng: pos.coords.longitude },
          pos.coords.accuracy,
        );
      },
      () => {
        // Denied or unavailable -- no-op. The map stays at DEFAULT_CENTER
        // for a manual pin, which is the D-10 fallback path.
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const eventHandlers = useMemo(
    () => ({
      dragend() {
        const marker = markerRef.current;
        if (marker != null) {
          const latlng = marker.getLatLng();
          onPositionChange({ lat: latlng.lat, lng: latlng.lng });
        }
      },
    }),
    [onPositionChange],
  );

  const center = position ?? DEFAULT_CENTER;

  return (
    <div>
      <div className="map-container">
        <MapContainer center={center} zoom={DEFAULT_ZOOM} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Marker
            draggable
            position={center}
            eventHandlers={eventHandlers}
            ref={markerRef}
          />
          <ClickToMove onMove={onPositionChange} />
        </MapContainer>
      </div>
      <p className="location-readout">
        Pin: {center.lat.toFixed(6)}, {center.lng.toFixed(6)}
        {accuracyMeters !== null ? ` (accuracy: ${accuracyMeters.toFixed(0)} m)` : ""}
      </p>
      <button type="button" onClick={() => onPositionChange(center)}>
        Confirm this location
      </button>
    </div>
  );
}
