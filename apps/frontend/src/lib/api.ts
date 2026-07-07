import axios from 'axios';
import type {
  ActionCard,
  Alert,
  AlertGeoJSON,
  CommunityHeatmapFeatureCollection,
  CommunityReport,
  CommunityReportResponse,
  Language,
  Livelihood,
} from '@hali/types';
import { env } from './env';

export const api = axios.create({
  baseURL: env.apiUrl,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

export async function fetchAlerts(
  lang: Language = 'sw',
  lat?: number,
  lng?: number,
  limit = 20,
): Promise<Alert[]> {
  const params: Record<string, string | number> = { lang, limit };
  if (lat != null) params.lat = lat;
  if (lng != null) params.lng = lng;
  const { data } = await api.get<Alert[]>('/api/alerts', { params });
  return data;
}

export async function fetchAlertsGeoJSON(
  lang: Language = 'sw',
  bbox = '21,-12,52,24',
  severity?: string,
  hazard?: string,
): Promise<AlertGeoJSON> {
  const params: Record<string, string> = { lang, bbox };
  if (severity) params.severity = severity;
  if (hazard) params.hazard = hazard;
  const { data } = await api.get<AlertGeoJSON>('/api/alerts/geojson', { params });
  return data;
}

export async function fetchActionCard(
  alertId: string,
  livelihood: Livelihood,
  lang: Language = 'en',
): Promise<ActionCard | null> {
  try {
    const { data } = await api.get<ActionCard>(`/api/alerts/${alertId}/action-card`, {
      params: { livelihood, lang },
    });
    return data;
  } catch {
    return null;
  }
}

export async function submitReport(report: CommunityReport): Promise<CommunityReportResponse> {
  const { data } = await api.post<CommunityReportResponse>('/api/reports', report);
  return data;
}

export async function fetchHeatmap(days = 7): Promise<CommunityHeatmapFeatureCollection> {
  const { data } = await api.get<CommunityHeatmapFeatureCollection>('/api/reports/heatmap', {
    params: { days },
  });
  return data;
}
