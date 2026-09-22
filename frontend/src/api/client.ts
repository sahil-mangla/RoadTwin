import type {
  ChainSeedResult,
  Report,
  ReportCreatePayload,
  ReportStatus,
  SchemaStatus,
} from "../types";

// Relative URLs so the Vite dev proxy (vite.config.ts) routes these to
// the FastAPI backend -- no hardcoded host/port here.
const REPORTS_URL = "/api/skeleton/reports";
const CHAIN_URL = "/api/skeleton/chain";
const SCHEMA_STATUS_URL = "/api/skeleton/schema-status";

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
