import type {
  AuthoritySegmentDetail,
  CitizenNotification,
  EnhancementInputs,
  Overview,
  PublicMap,
  PublicSegmentDetail,
  QueueItem,
  StaffUser,
} from "../intelTypes";

/** Thrown with the HTTP status so callers can tell "not logged in" (401) apart. */
export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // not JSON
    }
    throw new ApiError(response.status, `${response.status}: ${detail}`);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

function sendJson<T>(url: string, method: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// --- Public, read-only (PMAP-02) ---
export const getPublicMap = () => request<PublicMap>("/api/public/map");
export const getPublicSegment = (id: string) => request<PublicSegmentDetail>(`/api/public/segments/${id}`);

// --- Staff auth (AUTH-01) ---
export const login = (email: string, password: string) =>
  sendJson<StaffUser>("/api/auth/login", "POST", { email, password });
export const logout = () => request<void>("/api/auth/logout", { method: "POST" });
export const whoAmI = () => request<StaffUser>("/api/auth/me");

// --- Authority dashboard (AUTH-02..06, RPWF-01) ---
export const getOverview = () => request<Overview>("/api/authority/overview");
export const getQueue = () => request<QueueItem[]>("/api/authority/queue");
export const getAuthoritySegment = (id: string) =>
  request<AuthoritySegmentDetail>(`/api/authority/segments/${id}`);
export const changeRepairStatus = (id: string, status: string, note: string | null) =>
  sendJson<{ repair_status: string; label: string; citizens_notified: number }>(
    `/api/authority/segments/${id}/repair-status`, "POST", { status, note },
  );
export const updateInputs = (id: string, inputs: EnhancementInputs) =>
  sendJson<AuthoritySegmentDetail>(`/api/authority/segments/${id}/inputs`, "PATCH", inputs);

// --- Citizen notifications (RPWF-02) ---
export const getMyNotifications = () => request<CitizenNotification[]>("/api/me/notifications");
export const markNotificationRead = (id: string) =>
  request<void>(`/api/me/notifications/${id}/read`, { method: "POST" });
