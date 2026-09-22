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
