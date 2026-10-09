import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Band, SegmentForecast } from "../intelTypes";

export const BAND_COLORS: Record<Band, string> = {
  Excellent: "#1a9850",
  Good: "#91cf60",
  Poor: "#e6b800",
  Critical: "#fc8d59",
  "Severely degraded": "#d73027",
};
export const NO_DATA_COLOR = "#9e9e9e";

export function bandColor(band: Band | null | undefined): string {
  return band ? BAND_COLORS[band] : NO_DATA_COLOR;
}

/** PRIO-03: every score shown to anyone carries this label. */
export function ProvisionalNote({ text }: { text?: string }) {
  return (
    <p className="provisional-note" role="note">
      <strong>Provisional:</strong>{" "}
      {text ?? "scores are tunable estimates, not validated engineering measurements."}
    </p>
  );
}

export function BandBadge({ band, score }: { band: Band | null; score: number | null }) {
  if (band === null || score === null) return <span className="band-badge no-data">no data</span>;
  return (
    <span className="band-badge" style={{ background: bandColor(band) }} title="Provisional score">
      {score.toFixed(0)} · {band}*
    </span>
  );
}

export function BandLegend() {
  return (
    <div className="band-legend">
      {(Object.keys(BAND_COLORS) as Band[]).map((b) => (
        <span key={b}>
          <i style={{ background: BAND_COLORS[b] }} /> {b}
        </span>
      ))}
      <span>
        <i style={{ background: NO_DATA_COLOR }} /> No data
      </span>
    </div>
  );
}

/** Inline SVG line of health over time (0-100), no chart library. */
export function Sparkline({ points, width = 260, height = 60 }: {
  points: { measured_at: string; health_score: number }[];
  width?: number;
  height?: number;
}) {
  if (points.length === 0) return <span className="muted">No health measurements yet.</span>;
  if (points.length === 1) {
    return <span className="muted">One measurement so far: {points[0].health_score.toFixed(0)}</span>;
  }
  const times = points.map((p) => new Date(p.measured_at).getTime());
  const t0 = Math.min(...times);
  const span = Math.max(...times) - t0 || 1;
  const xy = points.map((p, i) => [
    ((times[i] - t0) / span) * (width - 8) + 4,
    height - 4 - (p.health_score / 100) * (height - 8),
  ]);
  return (
    <svg width={width} height={height} className="sparkline" role="img" aria-label="Health history">
      <line x1="0" x2={width} y1={height - 4 - 0.4 * (height - 8)} y2={height - 4 - 0.4 * (height - 8)} className="threshold" />
      <polyline points={xy.map(([x, y]) => `${x},${y}`).join(" ")} />
      {xy.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.5" />)}
    </svg>
  );
}

export interface MapSegment {
  id: string;
  label: string;
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
  band: Band | null;
  detail: string;
}

export interface MapPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
  radius: number;
}

/** Road-health map: segments coloured by band, optional damage points. */
export function HealthMap({ segments, points = [], selectedId, onSelect, height = 420 }: {
  segments: MapSegment[];
  points?: MapPoint[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  height?: number;
}) {
  const lats = segments.flatMap((s) => [s.start_lat, s.end_lat]).concat(points.map((p) => p.lat));
  const lngs = segments.flatMap((s) => [s.start_lng, s.end_lng]).concat(points.map((p) => p.lng));
  const bounds: [[number, number], [number, number]] | undefined = lats.length
    ? [[Math.min(...lats) - 0.002, Math.min(...lngs) - 0.002], [Math.max(...lats) + 0.002, Math.max(...lngs) + 0.002]]
    : undefined;

  return (
    <div className="intel-map" style={{ height }}>
      <MapContainer
        key={bounds ? bounds.flat().join(",") : "empty"}
        bounds={bounds}
        center={bounds ? undefined : [12.9716, 77.5946]}
        zoom={bounds ? undefined : 13}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {segments.map((s) => {
          const color = bandColor(s.band);
          const selected = s.id === selectedId;
          const handlers = { click: () => onSelect?.(s.id) };
          const zeroLength = s.start_lat === s.end_lat && s.start_lng === s.end_lng;
          const tip = <Tooltip>{s.label}: {s.detail}</Tooltip>;
          return zeroLength ? (
            <CircleMarker key={s.id} center={[s.start_lat, s.start_lng]} radius={selected ? 12 : 9}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.85, weight: selected ? 4 : 2 }}
              eventHandlers={handlers}>{tip}</CircleMarker>
          ) : (
            <Polyline key={s.id} positions={[[s.start_lat, s.start_lng], [s.end_lat, s.end_lng]]}
              pathOptions={{ color, weight: selected ? 10 : 7, opacity: 0.9 }}
              eventHandlers={handlers}>{tip}</Polyline>
          );
        })}
        {points.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={p.radius}
            pathOptions={{ color: "#333", fillColor: "#fff", fillOpacity: 0.9, weight: 1.5 }}>
            <Popup>{p.label}</Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}

export function OutlookView({ outlook }: { outlook: SegmentForecast }) {
  const d = outlook.deterioration;
  const f = outlook.forecast;
  return (
    <div className="outlook">
      <p>
        <strong>Trend:</strong>{" "}
        {d.status === "ok" && d.rate_per_day !== null
          ? `${d.trend} (${d.rate_per_day > 0 ? "+" : ""}${d.rate_per_day.toFixed(2)} pts/day)`
          : "Insufficient data"}
      </p>
      {f.status === "ok" ? (
        <table className="compact">
          <thead><tr><th>In</th><th>Predicted health</th><th>Failure risk</th><th>Confidence</th></tr></thead>
          <tbody>
            {f.horizons.map((h) => (
              <tr key={h.horizon_days} title={h.explanation ?? ""}>
                <td>{h.horizon_days} days</td>
                <td><BandBadge band={h.predicted_band} score={h.predicted_health_score} /></td>
                <td>{h.failure_probability === null ? "–" : `${Math.round(h.failure_probability * 100)}%`}</td>
                <td>{h.confidence === null ? "–" : `${Math.round(h.confidence * 100)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="muted">
          Forecast withheld until there is enough history:
          <ul>{f.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
      )}
      {f.status === "ok" && f.horizons[0]?.explanation && <p className="muted small">{f.horizons[0].explanation}</p>}
    </div>
  );
}
