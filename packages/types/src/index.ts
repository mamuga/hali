export type HazardType =
  | "flood"
  | "drought"
  | "locust"
  | "cyclone"
  | "heatwave"
  | "landslide"
  | "wildfire"
  /** An outbreak (e.g. post-flood cholera). `health` remains for general advisories. */
  | "epidemic"
  | "health"
  | "other";

export type Severity = "green" | "orange" | "red";

export type Language =
  | "sw"
  | "so"
  | "am"
  | "om"
  | "ar"
  | "en"
  | "fr"
  | "ti"
  | "lg"
  | "aa";

/** Languages where LLM quality is weaker; the backend may serve English instead. */
export type LowResourceLanguage = "ti" | "lg" | "aa";

export type Livelihood =
  | "farmer"
  | "pastoralist"
  | "agropastoralist"
  | "fisherfolk"
  | "urban"
  | "trader"
  | "displaced";

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
  /**
   * Set when the text is not actually in `language` — a low-resource
   * translation fell below the clarity floor and English was served instead.
   * null/undefined means the content genuinely is in the requested language.
   */
  fallback_language?: Language | null;
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

/**
 * `national` alerts (IFRC appeals, WHO outbreak notices) cover a whole country.
 * They are real, but drawn alongside district footprints they hide them, so the
 * map keeps them on a separate toggle.
 */
export type AlertScope = "local" | "national";

export interface AlertFeatureProperties {
  id: string;
  hazard_type: HazardType;
  severity: Severity;
  source?: string;
  scope?: AlertScope;
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

export interface CountryProperties {
  iso2: string;
  name: string;
}

export interface CountriesGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSON.MultiPolygon | GeoJSON.Polygon;
    properties: CountryProperties;
  }>;
}

export interface CompoundRiskProperties {
  iso2: string;
  country: string;
  /** 0-100. 100 means the whole country is under a red alert. */
  compound_risk_score: number;
  dominant_hazard: HazardType;
  alert_count: number;
  /** Country-wide IFRC/WHO advisories, excluded from the area figures. */
  national_advisories: number;
  max_severity: Severity;
  /** Land under at least one subnational alert — unioned, so never double-counted. */
  alert_area_km2: number;
  country_area_km2: number;
  alert_area_pct: number;
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
  /** Country-wide advisory vs a subnational hazard footprint. */
  scope: AlertScope;
}

export interface SpatialAnalysis {
  location: { lat: number; lng: number };
  country: string | null;
  nearest_alerts: NearestAlert[];
  nearby_reports_7d: number;
  report_breakdown: Array<{ label: string; count: number }>;
  emerging_hotspots_nearby: number;
}

export interface AoiAlert {
  id: string;
  hazard_type: HazardType;
  severity: Severity;
  headline: string;
  valid_to: string | null;
  population_exposed: number | null;
  /** Area of this alert that falls inside the drawn shape. */
  overlap_km2: number;
}

/** Result of analysing a user-drawn area of interest. */
export interface PolygonQueryResult {
  area_km2: number;
  /** Every intersecting alert. `alerts` is capped at 50 for display. */
  alert_count: number;
  alerts: AoiAlert[];
  report_count: number;
  report_hazards: HazardType[];
  emerging_hotspots: number;
  /** null means no population grid is loaded — never "nobody lives here". */
  population_estimate: number | null;
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
