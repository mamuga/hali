import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { fetchAlertsGeoJSON, fetchHeatmap } from '@/lib/api';
import type { CommunityHeatmapFeatureCollection, Language } from '@hali/types';

import iconUrl from 'leaflet/dist/images/marker-icon.png';
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

const SEV_COLOUR: Record<string, string> = {
  red: '#dc2626',
  orange: '#ea580c',
  green: '#16a34a',
};

interface Props {
  lang?: Language;
}

function heatPoints(heatData: CommunityHeatmapFeatureCollection) {
  return heatData.features
    .filter((f) => f.geometry.type === 'Point')
    .map((f) => {
      const [lng, lat] = f.geometry.coordinates;
      return [lat, lng, f.properties.intensity || 1] as [number, number, number];
    });
}

export function HaliMap({ lang = 'sw' }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const alertLayerRef = useRef<L.GeoJSON | null>(null);
  const heatLayerRef = useRef<L.Layer | null>(null);
  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = L.map(ref.current, { center: [2, 38], zoom: 5 });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);
    L.control.scale({ imperial: false }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    setLoading(true);
    setError(false);

    fetchAlertsGeoJSON(lang)
      .then((geojson) => {
        if (alertLayerRef.current) mapRef.current?.removeLayer(alertLayerRef.current);

        const layer = L.geoJSON(geojson, {
          style: (f) => ({
            color: SEV_COLOUR[f?.properties?.severity ?? 'green'] ?? '#16a34a',
            fillColor: SEV_COLOUR[f?.properties?.severity ?? 'green'] ?? '#16a34a',
            fillOpacity: 0.2,
            weight: 2,
            opacity: 0.85,
          }),
          onEachFeature(feature, layer) {
            const p = feature.properties;
            if (!p) return;
            const sev = p.severity ?? 'green';
            const colour = SEV_COLOUR[sev] ?? '#16a34a';
            layer.bindPopup(
              `<div class="hali-popup-title">${p.headline ?? `${p.hazard_type} alert`}</div>
              <div style="margin-top:6px;display:flex;gap:6px;align-items:center">
                <span class="hali-popup-badge" style="background:${colour}22;color:${colour}">
                  <span style="width:6px;height:6px;border-radius:50%;background:${colour};display:inline-block"></span>
                  ${sev.toUpperCase()}
                </span>
                <span style="font-size:11px;opacity:0.7">${(p.affected_countries ?? []).join(', ')}</span>
              </div>`,
              { maxWidth: 260 },
            );
          },
        }).addTo(mapRef.current);

        alertLayerRef.current = layer;
        setCount(geojson.features.length);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [lang]);

  useEffect(() => {
    if (!mapRef.current) return;
    fetchHeatmap(7)
      .then(async (heatData) => {
        if (heatLayerRef.current) mapRef.current?.removeLayer(heatLayerRef.current);
        const points = heatPoints(heatData);
        if (points.length > 0) {
          await import('leaflet.heat');
          const heat = (L as typeof L & { heatLayer: (p: [number, number, number][], o: Record<string, number>) => L.Layer }).heatLayer(points, {
            radius: 28,
            blur: 18,
            maxZoom: 10,
          });
          heat.addTo(mapRef.current!);
          heatLayerRef.current = heat;
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="relative h-full w-full">
      <div className="absolute right-3 top-3 z-[1000] flex gap-2">
        {loading && (
          <div className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-sm">
            <Loader2 className="h-3 w-3 animate-spin" />
            Loading
          </div>
        )}
        {!loading && !error && count > 0 && (
          <div className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-sm">
            {count} active alert{count !== 1 ? 's' : ''}
          </div>
        )}
        {error && (
          <div className="flex items-center gap-1.5 rounded-full border border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
            <AlertTriangle className="h-3 w-3" />
            Failed to load
          </div>
        )}
      </div>

      <div className="absolute bottom-6 left-3 z-[1000] rounded-lg border border-border bg-card/95 p-2.5 shadow-md backdrop-blur-sm">
        {[
          { sev: 'red', label: 'High risk' },
          { sev: 'orange', label: 'Medium risk' },
          { sev: 'green', label: 'Low risk' },
        ].map(({ sev, label }) => (
          <div key={sev} className="mb-1 flex items-center gap-2 last:mb-0">
            <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: SEV_COLOUR[sev] }} />
            <span className="text-[11px] text-muted-foreground">{label}</span>
          </div>
        ))}
      </div>

      <div ref={ref} className="h-full w-full" aria-label="HALI early warning map - East Africa" role="application" />
    </div>
  );
}
