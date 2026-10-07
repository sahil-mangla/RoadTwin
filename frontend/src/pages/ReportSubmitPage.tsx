import { useState } from "react";
import type { FormEvent } from "react";
import { createReportWithImage, probeImageExifGps } from "../api/client";
import { LocationPicker, type LatLngLiteral } from "../components/LocationPicker";
import { validateReportDraft } from "../types";
import type { Report, ReportSubmitDraft } from "../types";

// Mirrors backend/core/config.py's Settings.gps_imprecise_threshold_meters
// (50 m default) -- a purely advisory threshold, never a submission block
// (D-11).
const GPS_IMPRECISE_THRESHOLD_METERS = 50;

const EMPTY_DRAFT: ReportSubmitDraft = {
  latitude: null,
  longitude: null,
  gpsAccuracyMeters: null,
  description: "",
  imageFile: null,
};

export function ReportSubmitPage() {
  const [draft, setDraft] = useState<ReportSubmitDraft>(EMPTY_DRAFT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Report | null>(null);
  const [exifNotice, setExifNotice] = useState(false);

  function handlePositionChange(pos: LatLngLiteral) {
    setDraft((prev) => ({ ...prev, latitude: pos.lat, longitude: pos.lng }));
    setExifNotice(false);
  }

  function handleGeolocationResult(pos: LatLngLiteral, accuracyMeters: number | null) {
    // A geolocation success is only a CANDIDATE pin -- it still requires
    // the citizen's explicit confirmation via LocationPicker's own confirm
    // control or a drag, exactly like the manual and EXIF-metadata paths
    // (D-10: no coordinate is ever submitted without being seen first).
    setDraft((prev) => ({
      ...prev,
      latitude: pos.lat,
      longitude: pos.lng,
      gpsAccuracyMeters: accuracyMeters,
    }));
  }

  // D-10 invariant: browser geolocation, the default map centre, and photo
  // EXIF are three sources of a CANDIDATE pin -- all three converge on the
  // one map confirmation control (LocationPicker's confirm/drag), and
  // there is no fourth path that reaches the submitted payload.
  function handleFileChange(file: File | null) {
    setDraft((prev) => ({ ...prev, imageFile: file }));
    setExifNotice(false);

    if (file === null || draft.latitude !== null) {
      // A location the citizen already chose (geolocation or manual pin)
      // wins -- photo metadata never silently overrides an explicit choice.
      return;
    }

    probeImageExifGps(file)
      .then((candidate) => {
        if (candidate.latitude !== null && candidate.longitude !== null) {
          setDraft((prev) => ({
            ...prev,
            latitude: candidate.latitude,
            longitude: candidate.longitude,
          }));
          setExifNotice(true);
        }
      })
      .catch(() => {
        // A photo with no GPS, or a probe failure (e.g. rate-limited), is
        // the ordinary case -- fail silently. The manual pin path always
        // remains available, and surfacing this as an error would make a
        // normal upload look broken.
      });
  }

  const validationMessage = validateReportDraft(draft);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (validationMessage !== null) {
      setError(validationMessage);
      return;
    }

    setSubmitting(true);
    try {
      const report = await createReportWithImage(draft);
      setCreated(report);
      setDraft(EMPTY_DRAFT);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <h2>Report road damage</h2>

      {created && (
        <p className="confirmation-banner" role="status">
          Report recorded — id <code>{created.id}</code>.
        </p>
      )}

      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <LocationPicker
          position={
            draft.latitude !== null && draft.longitude !== null
              ? { lat: draft.latitude, lng: draft.longitude }
              : null
          }
          accuracyMeters={draft.gpsAccuracyMeters}
          onPositionChange={handlePositionChange}
          onGeolocationResult={handleGeolocationResult}
        />

        {exifNotice && (
          <p className="advisory-banner">
            This location came from your photo's metadata. Confirm or drag
            the pin before submitting.
          </p>
        )}

        {draft.gpsAccuracyMeters !== null &&
          draft.gpsAccuracyMeters > GPS_IMPRECISE_THRESHOLD_METERS && (
            <p className="advisory-banner">
              Your location may be imprecise (±{draft.gpsAccuracyMeters.toFixed(0)} m).
              You can still submit, or drag the pin to correct it.
            </p>
          )}

        <label>
          Photo
          <input
            type="file"
            accept="image/jpeg,image/png"
            onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
          />
        </label>

        <label>
          Description (optional)
          <textarea
            value={draft.description}
            onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
          />
        </label>

        {validationMessage && <p className="advisory-banner">{validationMessage}</p>}

        <button type="submit" disabled={submitting || validationMessage !== null}>
          {submitting ? "Submitting..." : "Submit report"}
        </button>
      </form>
    </section>
  );
}
