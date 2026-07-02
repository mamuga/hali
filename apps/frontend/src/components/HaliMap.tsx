import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import 'leaflet.heat';
import { useEffect } from 'react';
import { GeoJSON, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet';
import type { AlertGeoJSON, CommunityHeatmapFeatureCollection, Severity } from '../lib/types';

function color(severity: Severity) {
  return severity === 'red' ? '#B42318' : severity === 'orange' ? '#B85C00' : '#0F6E56';
}

function Heatmap({ heatmap }: { heatmap: CommunityHeatmapFeatureCollection }) {
  const map = useMap();
  useEffect(() => {
    const points = heatmap.features.map((feature) => [feature.geometry.coordinates[1], feature.geometry.coordinates[0], feature.properties.intensity] as [number, number, number]);
    const layer = L.heatLayer(points, { radius: 28, blur: 18, maxZoom: 8 }).addTo(map);
    return () => { layer.remove(); };
  }, [heatmap, map]);
  return null;
}

export function HaliMap({ alerts, heatmap, loading }: { alerts: AlertGeoJSON; heatmap: CommunityHeatmapFeatureCollection; loading?: boolean }) {
  return <section className="map-shell" aria-label="East Africa alert map">{loading && <div className="map-loading">Loading map layers</div>}<MapContainer center={[4, 39]} zoom={5} minZoom={4} className="hali-map"><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><GeoJSON key={JSON.stringify(alerts)} data={alerts} style={(feature) => ({ color: color(feature?.properties.severity), weight: 2, fillOpacity: 0.22 })} onEachFeature={(feature, layer) => { layer.bindPopup(`<strong>${feature.properties.headline}</strong><br/>${feature.properties.hazard_type} · ${feature.properties.severity}<br/>${feature.properties.affected_countries.join(', ')}`); }} /><Heatmap heatmap={heatmap} /></MapContainer></section>;
}
