import { useEffect, useState } from "react";
import { getPublicMap, getPublicSegment } from "../api/intel";
import { BandBadge, BandLegend, HealthMap, OutlookView, ProvisionalNote, Sparkline } from "../components/intel";
import type { PublicMap, PublicSegmentDetail } from "../intelTypes";

const DAMAGE_NAMES: Record<string, string> = {
  D00: "Longitudinal crack",
  D10: "Transverse crack",
  D20: "Alligator crack",
  D40: "Pothole",
};

/** PMAP-01: public, read-only map of road health, damage clusters, reports and trends. */
export function PublicMapPage() {
  const [data, setData] = useState<PublicMap | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PublicSegmentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getPublicMap().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDetail(null);
    getPublicSegment(selected).then(setDetail).catch((e: Error) => setError(e.message));
  }, [selected]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <p>Loading map…</p>;

  // A damage cluster = a canonical report plus its near-duplicates.
  const clusters = data.reports.filter((r) => !r.is_duplicate);

  return (
    <section>
      <h2>Road health map</h2>
      <ProvisionalNote text={data.note} />
      <BandLegend />
      <HealthMap
        segments={data.segments.map((s) => ({
          ...s,
          label: s.segment_identifier,
          detail: `${s.health_score === null ? "no score" : s.health_score.toFixed(0)} (${s.band ?? "no data"}), ${s.trend}`,
        }))}
        points={clusters.map((r) => ({
          id: r.id,
          lat: r.latitude,
          lng: r.longitude,
          radius: 4 + Math.min(r.duplicate_count, 6),
          label: `${r.damage_types.map((t) => DAMAGE_NAMES[t] ?? t).join(", ") || "Damage"}${
            r.worst_severity ? ` (${r.worst_severity})` : ""
          } · ${1 + r.duplicate_count} report(s) · ${r.status.replace("_", " ")}`,
        }))}
        selectedId={selected}
        onSelect={setSelected}
      />
      <p className="muted small">
        Lines and dots are road segments coloured by health; white circles are damage clusters
        (bigger = more reports). Click a segment for details.
      </p>
      {data.segments.length === 0 && <p>No road segments yet — they appear once reports are analysed.</p>}

      {selected && (
        <div className="panel">
          {!detail ? (
            <p>Loading…</p>
          ) : (
            <>
              <h3>
                {detail.segment.segment_identifier}{" "}
                <BandBadge band={detail.segment.band} score={detail.segment.health_score} />
              </h3>
              <p>
                {detail.segment.report_count} report(s) · repair status:{" "}
                <strong>{detail.segment.repair_status.replace("_", " ")}</strong>
              </p>
              <h4>Health over time</h4>
              <Sparkline points={detail.health_history} />
              <h4>Damage seen</h4>
              <ul>
                {Object.entries(detail.damage_composition).map(([t, n]) => (
                  <li key={t}>{DAMAGE_NAMES[t] ?? t}: {n}</li>
                ))}
              </ul>
              <h4>Outlook</h4>
              <OutlookView outlook={detail.outlook} />
            </>
          )}
        </div>
      )}
    </section>
  );
}
