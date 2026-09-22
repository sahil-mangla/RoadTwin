import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { createReport, listReports } from "../api/client";
import type { Report } from "../types";

// Pre-fill values so the page is usable in one click (Bengaluru coords).
const DEFAULT_LATITUDE = "12.9716";
const DEFAULT_LONGITUDE = "77.5946";

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

  const [latitude, setLatitude] = useState(DEFAULT_LATITUDE);
  const [longitude, setLongitude] = useState(DEFAULT_LONGITUDE);
  const [accuracy, setAccuracy] = useState("");
  const [description, setDescription] = useState("");

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
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await createReport({
        latitude: Number(latitude),
        longitude: Number(longitude),
        gps_accuracy_meters: accuracy === "" ? null : Number(accuracy),
        description: description === "" ? null : description,
      });
      setReports((prev) => [created, ...prev]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
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
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
