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
