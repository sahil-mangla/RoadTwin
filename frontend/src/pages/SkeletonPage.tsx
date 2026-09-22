import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  createReport,
  getSchemaStatus,
  listReports,
  seedChain,
  updateReportStatus,
} from "../api/client";
import type { Report, ReportStatus, SchemaStatus } from "../types";

// Pre-fill values so the page is usable in one click (Bengaluru coords).
const DEFAULT_LATITUDE = "12.9716";
const DEFAULT_LONGITUDE = "77.5946";

// The four D-06 lifecycle values, iterated to build the status select's
// options -- the value itself is also the label, so no separate literal
// label list exists anywhere in this file.
const REPORT_STATUSES: ReportStatus[] = [
  "unverified",
  "corroborated",
  "evidence_confirmed",
  "rejected",
];

function formatAccuracy(meters: number | null): string {
  return meters === null ? "no accuracy reported" : `${meters} m`;
}

function shortenId(id: string): string {
  return id.slice(0, 8);
}

export function SkeletonPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [schemaStatus, setSchemaStatus] = useState<SchemaStatus | null>(null);

  const [latitude, setLatitude] = useState(DEFAULT_LATITUDE);
  const [longitude, setLongitude] = useState(DEFAULT_LONGITUDE);
  const [accuracy, setAccuracy] = useState("");
  const [description, setDescription] = useState("");

  const refreshSchemaStatus = useCallback(async () => {
    try {
      setSchemaStatus(await getSchemaStatus());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    listReports()
      .then((data) => {
        setReports(data);
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });
    void refreshSchemaStatus();
  }, [refreshSchemaStatus]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    // `noValidate` (below) disables the browser's own `required` check so that
    // out-of-range values like latitude=91 reach the backend's 422 error path
    // instead of being blocked client-side. That also means an empty field is
    // no longer rejected here -- and `Number("")` is 0, a legal coordinate, so
    // an empty submit would otherwise silently persist a report at (0, 0).
    const parsedLatitude = Number(latitude);
    const parsedLongitude = Number(longitude);
    if (
      latitude.trim() === "" ||
      longitude.trim() === "" ||
      !Number.isFinite(parsedLatitude) ||
      !Number.isFinite(parsedLongitude)
    ) {
      setError("Latitude and longitude are required.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await createReport({
        latitude: parsedLatitude,
        longitude: parsedLongitude,
        gps_accuracy_meters: accuracy === "" ? null : Number(accuracy),
        description: description === "" ? null : description,
      });
      setReports((prev) => [created, ...prev]);
      await refreshSchemaStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSeedChain() {
    setSeeding(true);
    setError(null);
    try {
      await seedChain();
      const data = await listReports();
      setReports(data);
      await refreshSchemaStatus();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSeeding(false);
    }
  }

  async function handleStatusChange(report: Report, status: ReportStatus) {
    setError(null);
    try {
      const updated = await updateReportStatus(report.id, status);
      setReports((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section>
      <h2>Schema status</h2>
      {schemaStatus && (
        <table>
          <thead>
            <tr>
              <th>Entity</th>
              <th>Row count</th>
            </tr>
          </thead>
          <tbody>
            {schemaStatus.entities.map((row) => (
              <tr key={row.entity}>
                <td>{row.entity}</td>
                <td>{row.count}</td>
              </tr>
            ))}
            <tr>
              <td>total</td>
              <td>{schemaStatus.total_rows}</td>
            </tr>
          </tbody>
        </table>
      )}
      <p>
        These are raw table row counts proving the Phase 1 schema is
        reachable. Pressing Seed twice increases the observation, health
        and prediction counts each time, because those three entities are
        append-only.
      </p>
      <button type="button" onClick={handleSeedChain} disabled={seeding}>
        {seeding ? "Seeding..." : "Seed 7-entity chain"}
      </button>

      <h2>Submit a report</h2>
      <p>
        These are raw schema fields straight from Postgres -- not
        intelligence-layer output. No clustering, health score, or
        forecast is computed at this stage of the project.
      </p>

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <label>
          Latitude
          <input
            type="number"
            min={-90}
            max={90}
            step="any"
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
            required
          />
        </label>
        <label>
          Longitude
          <input
            type="number"
            min={-180}
            max={180}
            step="any"
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
            required
          />
        </label>
        <label>
          GPS accuracy (meters, optional)
          <input
            type="number"
            min={0}
            step="any"
            value={accuracy}
            onChange={(e) => setAccuracy(e.target.value)}
          />
        </label>
        <label>
          Description
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Submitting..." : "Submit"}
        </button>
      </form>

      <h2>Reports</h2>
      {loading ? (
        <p>Loading...</p>
      ) : reports.length === 0 ? (
        <p>No reports yet -- submit the form above to create the first one.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Latitude</th>
              <th>Longitude</th>
              <th>Accuracy</th>
              <th>Description</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report) => (
              <tr key={report.id}>
                <td>{shortenId(report.id)}</td>
                <td>{report.latitude.toFixed(4)}</td>
                <td>{report.longitude.toFixed(4)}</td>
                <td>{formatAccuracy(report.gps_accuracy_meters)}</td>
                <td>{report.description ?? "--"}</td>
                <td>
                  <span className="status-badge">{report.status}</span>
                  <select
                    value={report.status}
                    onChange={(e) =>
                      handleStatusChange(report, e.target.value as ReportStatus)
                    }
                  >
                    {REPORT_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
