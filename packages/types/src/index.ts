export type HazardType =
  | "flood"
  | "drought"
  | "locust"
  | "cyclone"
  | "health"
  | "other";

export type Severity = "green" | "orange" | "red";

export type Language = "sw" | "so" | "am" | "om" | "ar" | "en";

export type Livelihood = "farmer" | "pastoralist" | "fisherfolk" | "urban";

export interface Alert {
  id: string;
  hazard_type: HazardType;
  severity: Severity;
  affected_countries: string[];
  valid_from: string | null;
  valid_to: string | null;
  processed_at: string | null;
  is_new?: boolean;
  headline?: string;
  body?: string;
  audio_url?: string | null;
  /** WorldPop estimate. null means "not computed yet", never "nobody lives here". */
  population_exposed?: number | null;
}

export interface AlertTranslation {
  alert_id: string;
  language: Language;
  headline: string;
  body: string;
  audio_url?: string | null;
}

export interface ActionCard {
  alert_id: string;
  livelihood: Livelihood;
  language: Language;
  steps: string;
}

export interface CommunityReport {
  lat: number;
  lng: number;
  hazard_type: HazardType;
  description: string;
}

export interface CommunityReportResponse extends CommunityReport {
  id: string;
  labels: string[];
  reported_at: string;
}

export interface AlertFeatureProperties {
  id: string;
  hazard_type: HazardType;
  severity: Severity;
  headline: string;
  body: string;
  affected_countries: string[];
  /** WorldPop estimate. null means "not computed yet", never "nobody lives here". */
  population_exposed: number | null;
  valid_from: string | null;
  valid_to: string | null;
}

export interface AlertGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.MultiPolygon;
    properties: AlertFeatureProperties;
  }>;
}

export interface CompoundRiskProperties {
  iso2: string;
  country: string;
  compound_risk_score: number;
  dominant_hazard: HazardType;
  alert_count: number;
  max_severity: Severity;
  overlap_km2: number;
  community_reports_14d: number;
}

export interface CompoundRiskGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.MultiPolygon;
    properties: CompoundRiskProperties;
  }>;
}

export interface EmergingHotspotProperties {
  id: string;
  report_count: number;
  dominant_hazard: HazardType;
  confidence: number;
  status: string;
  first_reported: string;
  detected_at: string;
}

export interface EmergingHotspotGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.Point;
    properties: EmergingHotspotProperties;
  }>;
}

export interface NearestAlert {
  id: string;
  hazard_type: HazardType;
  severity: Severity;
  headline: string;
  dist_km: number;
  valid_to: string | null;
  population_exposed: number | null;
}

export interface SpatialAnalysis {
  location: { lat: number; lng: number };
  country: string | null;
  nearest_alerts: NearestAlert[];
  nearby_reports_7d: number;
  report_breakdown: Array<{ label: string; count: number }>;
  emerging_hotspots_nearby: number;
}

export interface SubscriptionCreate {
  phone_number: string;
  channel?: "sms" | "whatsapp" | "both";
  language?: Language;
  livelihood?: Livelihood;
  preferred_iso2?: string | null;
  lat?: number | null;
  lng?: number | null;
}

export interface SubscriptionResponse {
  id: string;
  channel: string;
  language: Language;
  livelihood: Livelihood;
  preferred_iso2: string | null;
  opted_in: boolean;
}

export interface CommunityHeatmapFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.Point;
    properties: {
      hazard_type: HazardType | null;
      reported_at: string;
      intensity: number;
    };
  }>;
}
