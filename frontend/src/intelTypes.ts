// Contracts for the Phase 6-7 intelligence APIs (public map, authority
// dashboard, citizen notifications). Mirrors backend/routes/{public,
// authority,auth,me}.py and backend/schemas/health.py.

export type Band = "Excellent" | "Good" | "Poor" | "Critical" | "Severely degraded";

export interface PublicSegment {
  id: string;
  segment_identifier: string;
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
  length_meters: number | null;
  health_score: number | null;
  band: Band | null;
  trend: string;
  repair_status: string;
  report_count: number;
  last_observed_at: string | null;
  provisional: boolean;
}

export interface PublicReport {
  id: string;
  latitude: number;
  longitude: number;
  observed_at: string;
  status: string;
  segment_id: string | null;
  damage_types: string[];
  worst_severity: string | null;
  is_duplicate: boolean;
  duplicate_count: number;
}

export interface PublicMap {
  note: string;
  segments: PublicSegment[];
  reports: PublicReport[];
}

export interface HorizonView {
  horizon_days: number;
  predicted_health_score: number;
  predicted_band: Band;
  failure_probability: number | null;
  confidence: number | null;
  method: string;
  explanation: string | null;
}

export interface SegmentForecast {
  segment_id: string;
  health_score: number | null;
  band: Band | null;
  measured_at: string | null;
  provisional: boolean;
  deterioration: {
    status: "ok" | "insufficient_data";
    rate_per_day: number | null;
    trend: string | null;
    reasons: string[];
    history: { points: number; span_days: number; observation_reports: number };
  };
  forecast: {
    status: "ok" | "insufficient_data";
    generated_at: string | null;
    horizons: HorizonView[];
    reasons: string[];
  };
  accuracy: {
    horizons: { horizon_days: number; evaluated: number; mean_absolute_error: number; bias: number; rmse: number }[];
  };
}

export interface PublicSegmentDetail {
  segment: PublicSegment;
  note: string;
  health_history: { measured_at: string; health_score: number; band: Band }[];
  damage_composition: Record<string, number>;
  outlook: SegmentForecast;
}

export interface StaffUser {
  id: string;
  email: string;
  role: string;
}

export interface QueueItem {
  rank: number;
  segment_id: string;
  segment_identifier: string;
  road_name: string | null;
  priority_score: number;
  urgency: "immediate" | "high" | "medium" | "low";
  recommended_action: string;
  explanation: string;
  health_score: number | null;
  band: Band | null;
  trend: string;
  repair_status: string;
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
  generated_at: string;
}

export interface Overview {
  note: string;
  segments: number;
  assessed_segments: number;
  average_health: number | null;
  band_counts: Record<Band, number>;
  critical_roads: number;
  rapidly_deteriorating: number;
  predicted_failures: number;
  repair_status_counts: Record<string, number>;
  top_priorities: QueueItem[];
}

export interface EvidenceItem {
  report_id: string;
  damage_type: string | null;
  severity: string | null;
  confidence: number | null;
  verification_score: number | null;
  observed_at: string;
  evidence_components: { contributions?: Record<string, number> } | null;
  counts_toward_health: boolean;
}

export interface PriorityComponents {
  factors: Record<string, number | null>;
  weights: Record<string, number>;
  contributions: Record<string, number>;
}

export interface AuthoritySegmentDetail {
  note: string;
  segment_id: string;
  segment_identifier: string;
  road_name: string | null;
  road_type: string | null;
  length_meters: number | null;
  start_lat: number;
  start_lng: number;
  end_lat: number;
  end_lng: number;
  traffic_exposure: number | null;
  near_vulnerable_location: boolean | null;
  repair_status: string;
  last_repaired_at: string | null;
  health_history: { measured_at: string; health_score: number; band: Band; burdens: Record<string, number> | null }[];
  damage_composition: Record<string, Record<string, number>>;
  evidence: EvidenceItem[];
  reports: { id: string; status: string; observed_at: string; community_upvotes: number; verification_score: number | null; is_duplicate: boolean }[];
  outlook: SegmentForecast;
  priority: {
    priority_score: number;
    urgency: string;
    recommended_action: string;
    explanation: string;
    components: PriorityComponents | null;
    generated_at: string;
  } | null;
  priority_history: { generated_at: string; priority_score: number; urgency: string }[];
  repair_events: { from_status: string; to_status: string; note: string | null; staff_email: string; created_at: string }[];
}

export interface EnhancementInputs {
  road_name?: string | null;
  road_type?: string | null;
  traffic_exposure?: number | null;
  near_vulnerable_location?: boolean | null;
}

export interface CitizenNotification {
  id: string;
  report_id: string;
  message: string;
  created_at: string;
  read: boolean;
}
