import type {
  ChainSeedResult,
  ExifGpsCandidate,
  Report,
  ReportCreatePayload,
  ReportImageUrl,
  ReportStatus,
  ReportSubmitDraft,
  SchemaStatus,
} from "../types";

// Relative URLs so the Vite dev proxy (vite.config.ts) routes these to
// the FastAPI backend -- no hardcoded host/port here.
const REPORTS_URL = "/api/skeleton/reports";
const CHAIN_URL = "/api/skeleton/chain";
const SCHEMA_STATUS_URL = "/api/skeleton/schema-status";

// The real citizen ingestion API (Phase 2), distinct from the /api/skeleton
// diagnostic endpoints above.
const CITIZEN_REPORTS_URL = "/api/reports";

/**
 * Builds a readable error message from a failed fetch response, including
 * the HTTP status and the FastAPI `detail` body when present, so a 422
 * from out-of-range coordinates reaches the user as text instead of a
 * silent no-op.
 */
async function toError(response: Response): Promise<Error> {
  let detail = "";
  try {
    const body = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    }
  } catch {
    // response body was not JSON -- fall back to status text only
  }
  const suffix = detail ? `: ${detail}` : "";
  return new Error(
    `Request failed with status ${response.status} ${response.statusText}${suffix}`,
  );
}

export async function listReports(): Promise<Report[]> {
  const response = await fetch(REPORTS_URL);
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as Report[];
}

export async function createReport(
  payload: ReportCreatePayload,
): Promise<Report> {
  const response = await fetch(REPORTS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as Report;
}

export async function getSchemaStatus(): Promise<SchemaStatus> {
  const response = await fetch(SCHEMA_STATUS_URL);
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as SchemaStatus;
}

export async function seedChain(): Promise<ChainSeedResult> {
  const response = await fetch(CHAIN_URL, { method: "POST" });
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as ChainSeedResult;
}

/**
 * Posts a citizen's report as multipart/form-data. Unlike `createReport`
 * above (which sends JSON and sets Content-Type by hand), a FormData body
 * must NEVER have its Content-Type set manually -- the browser generates
 * the multipart boundary itself, and an explicit header would produce a
 * body the server cannot parse. `credentials: "include"` lets the
 * `rt_device_id` cookie round-trip; without it the device identity is
 * re-minted on every request and attribution silently breaks.
 */
export async function createReportWithImage(draft: ReportSubmitDraft): Promise<Report> {
  const formData = new FormData();
  if (draft.imageFile) {
    formData.append("image", draft.imageFile);
  }
  formData.append("latitude", String(draft.latitude));
  formData.append("longitude", String(draft.longitude));
  if (draft.gpsAccuracyMeters !== null) {
    formData.append("gps_accuracy_meters", String(draft.gpsAccuracyMeters));
  }
  if (draft.description !== "") {
    formData.append("description", draft.description);
  }

  const response = await fetch(CITIZEN_REPORTS_URL, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (response.status === 429) {
    // Surface the wait time explicitly rather than leaving the citizen
    // with only the bare "too many requests" detail string -- a silent
    // no-op or an unexplained failure would violate D-06's intent that a
    // rate-limit rejection is always legible, never a dead end.
    const retryAfter = response.headers.get("Retry-After");
    const waitText = retryAfter ? ` Please wait about ${retryAfter} seconds and try again.` : "";
    const body = await response.json().catch(() => null);
    const detail = body && typeof body.detail === "string" ? body.detail : "Too many requests.";
    throw new Error(`${detail}${waitText}`);
  }
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as Report;
}

/**
 * Probes a photo's EXIF GPS as a candidate pin position. Follows
 * `createReportWithImage` exactly: no manual Content-Type, credentials
 * included, and the shared `toError` helper for failures.
 */
export async function probeImageExifGps(file: File): Promise<ExifGpsCandidate> {
  const formData = new FormData();
  formData.append("image", file);

  const response = await fetch(`${CITIZEN_REPORTS_URL}/exif-gps-probe`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as ExifGpsCandidate;
}

export async function getReportImageUrl(id: string): Promise<ReportImageUrl> {
  const response = await fetch(`${CITIZEN_REPORTS_URL}/${id}/image-url`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw await toError(response);
  }
  const body = (await response.json()) as { url: string; expires_in_seconds: number };
  return { url: body.url, expiresInSeconds: body.expires_in_seconds };
}

export async function updateReportStatus(
  id: string,
  status: ReportStatus,
): Promise<Report> {
  const response = await fetch(`${REPORTS_URL}/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    throw await toError(response);
  }
  return (await response.json()) as Report;
}
