import axios from 'axios';
import type { ActionCard, Alert, AlertGeoJSON, CommunityHeatmapFeatureCollection, CommunityReport, CommunityReportResponse, Language, Livelihood } from './types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const client = axios.create({ baseURL: API_URL, timeout: 12000 });

export async function fetchAlerts(lang: Language = 'en'): Promise<Alert[]> {
  const { data } = await client.get<Alert[]>('/api/alerts', { params: { lang } });
  return data;
}

export async function fetchAlertsGeoJSON(lang: Language = 'sw'): Promise<AlertGeoJSON> {
  const { data } = await client.get<AlertGeoJSON>('/api/alerts/geojson', { params: { lang } });
  return data;
}

export async function fetchActionCard(alertId: string, livelihood: Livelihood, lang: Language): Promise<ActionCard> {
  const { data } = await client.get<ActionCard>(`/api/alerts/${alertId}/action-card`, { params: { livelihood, lang } });
  return data;
}

export async function submitReport(report: CommunityReport): Promise<CommunityReportResponse> {
  const { data } = await client.post<CommunityReportResponse>('/api/reports', report);
  return data;
}

export async function fetchHeatmap(days = 7): Promise<CommunityHeatmapFeatureCollection> {
  const { data } = await client.get<CommunityHeatmapFeatureCollection>('/api/reports/heatmap', { params: { days } });
  return data;
}
