import { useEffect, useState } from 'react';
import { HaliMap } from '../components/HaliMap';
import { fetchAlertsGeoJSON, fetchHeatmap } from '../lib/api';
import type { AlertGeoJSON, CommunityHeatmapFeatureCollection } from '../lib/types';

const emptyAlerts: AlertGeoJSON = { type: 'FeatureCollection', features: [] };
const emptyHeatmap: CommunityHeatmapFeatureCollection = { type: 'FeatureCollection', features: [] };

export function MapView() {
  const [alerts, setAlerts] = useState(emptyAlerts);
  const [heatmap, setHeatmap] = useState(emptyHeatmap);
  const [loading, setLoading] = useState(true);
  useEffect(() => { Promise.all([fetchAlertsGeoJSON(), fetchHeatmap()]).then(([a, h]) => { setAlerts(a); setHeatmap(h); }).finally(() => setLoading(false)); }, []);
  return <main className="page page-map"><header className="page-header"><h1>Alert Map</h1></header><HaliMap alerts={alerts} heatmap={heatmap} loading={loading} /></main>;
}
