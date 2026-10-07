// TypeScript contracts mirroring backend/schemas/report.py exactly.
// These are raw Phase 1 schema fields, not intelligence-layer output.

/**
 * The four Report/Detection status lifecycle values locked by D-06.
 * `rejected` is reserved for the v2 moderation-flag path (MODR-01) --
 * it exists in the union now so the column never needs a later migration,
 * even though nothing in this phase transitions a report to it.
 */
export type ReportStatus =
  | 'unverified'
  | 'corroborated'
  | 'evidence_confirmed'
  | 'rejected';

export interface ReportCreatePayload {
  latitude: number;
  longitude: number;
  gps_accuracy_meters: number | null;
  description: string | null;
  source?: string;
}

export interface Report {
  id: string;
  latitude: number;
  longitude: number;
  gps_accuracy_meters: number | null;
  timestamp: string;
  source: string;
  description: string | null;
  status: ReportStatus;
  community_upvotes: number;
  verification_score: number | null;
  created_at: string;
}

// Mirrors backend/schemas/report.py's ReportImageUrl and ExifGpsCandidate.

export interface ReportImageUrl {
  url: string;
  expiresInSeconds: number;
}

export interface ExifGpsCandidate {
  latitude: number | null;
  longitude: number | null;
  source: string;
}

/** The single authoritative in-progress citizen submission draft. */
export interface ReportSubmitDraft {
  latitude: number | null;
  longitude: number | null;
  gpsAccuracyMeters: number | null;
  description: string;
  imageFile: File | null;
}

/**
 * Pure validation -- exists only so the submit button cannot fire a request
 * that cannot succeed. The server's Pydantic validation remains the sole
 * authority (Phase 1 CR-01); this never replaces it.
 */
export function validateReportDraft(draft: ReportSubmitDraft): string | null {
  if (draft.latitude === null || draft.longitude === null) {
    return "Please confirm a location on the map before submitting.";
  }
  if (draft.latitude < -90 || draft.latitude > 90) {
    return "Latitude must be between -90 and 90.";
  }
  if (draft.longitude < -180 || draft.longitude > 180) {
    return "Longitude must be between -180 and 180.";
  }
  if (draft.imageFile === null) {
    return "Please attach a photo of the road damage.";
  }
  return null;
}

// Mirrors backend/schemas/skeleton.py exactly.

/** One row of a live per-entity row count from GET /api/skeleton/schema-status. */
export interface EntityCount {
  entity: string;
  count: number;
}

/** The full schema-status panel payload -- seven entities plus their sum. */
export interface SchemaStatus {
  entities: EntityCount[];
  total_rows: number;
}

/** The seven ids written by one POST /api/skeleton/chain call. */
export interface ChainSeedResult {
  report_id: string;
  detection_id: string;
  road_segment_id: string;
  road_observation_id: string;
  road_health_id: string;
  prediction_id: string;
  maintenance_recommendation_id: string;
  seeded_at: string;
}
