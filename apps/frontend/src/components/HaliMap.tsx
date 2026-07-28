import { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AlertTriangle, Loader2 } from 'lucide-react';
import {
  analyseLocation,
  fetchAlertsGeoJSON,
  fetchCompoundRisk,
  fetchEmergingHotspots,
  fetchHeatmap,
} from '@/lib/api';
import { createIcpacLayers } from '@/lib/icpacLayers';
import type {
  CommunityHeatmapFeatureCollection,
  CompoundRiskGeoJSON,
  Language,
  SpatialAnalysis,
} from '@hali/types';
import { AnalysisPanel } from './AnalysisPanel';
import { RiskRanking, riskColour } from './RiskRanking';
import { TemporalSlider, offsetToDate } from './TemporalSlider';

import iconUrl from 'leaflet/dist/images/marker-icon.png';
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

// leaflet.heat is a plain UMD script that expects a preexisting global `L`
// rather than importing it, so it must be exposed on window before it loads.
(window as unknown as { L: typeof L }).L = L;

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
  const hotspotLayerRef = useRef<L.LayerGroup | null>(null);
  const riskLayerRef = useRef<L.GeoJSON | null>(null);

  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  const [error, setError] = useState(false);
  const [dayOffset, setDayOffset] = useState<number | null>(null);
  const [risk, setRisk] = useState<CompoundRiskGeoJSON | null>(null);
  const [analysis, setAnalysis] = useState<SpatialAnalysis | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [analysisError, setAnalysisError] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);

  // Keep the latest language available to the map click handler, which is bound
  // once and would otherwise capture the value from first render.
  const langRef = useRef(lang);
  langRef.current = lang;

  const runAnalysis = useCallback(async (lat: number, lng: number) => {
    setPanelOpen(true);
    setAnalysing(true);
    setAnalysisError(false);
    try {
      setAnalysis(await analyseLocation(lat, lng, langRef.current));
    } catch {
      setAnalysisError(true);
    } finally {
      setAnalysing(false);
    }
  }, []);

  // ── Map bootstrap ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = L.map(ref.current, { center: [2, 38], zoom: 5 });

    const base = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
      maxZoom: 18,
    }).addTo(map);

    L.control.scale({ imperial: false }).addTo(map);

    // ICPAC's own authoritative layers, toggleable over HALI's alert zones.
    L.control
      .layers({ 'Street map': base }, createIcpacLayers(), { collapsed: true, position: 'topright' })
      .addTo(map);

    map.on('click', (e: L.LeafletMouseEvent) => {
      void runAnalysis(e.latlng.lat, e.latlng.lng);
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [runAnalysis]);

  // ── Alert zones (re-fetched on language or playback change) ─────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    setLoading(true);
    setError(false);

    const fromDate = dayOffset != null ? offsetToDate(0) : undefined;
    const toDate = dayOffset != null ? offsetToDate(dayOffset) : undefined;

    fetchAlertsGeoJSON(lang, '21,-12,52,24', undefined, undefined, fromDate, toDate)
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
            // population_exposed is null until WorldPop answers; omit the line
            // rather than claim zero people are affected.
            const population =
              p.population_exposed != null
                ? `<div style="font-size:11px;opacity:0.75;margin-top:4px">~${Number(
                    p.population_exposed,
                  ).toLocaleString()} people in zone</div>`
                : '';
            layer.bindPopup(
              `<div class="hali-popup-title">${p.headline ?? `${p.hazard_type} alert`}</div>
              <div style="margin-top:6px;display:flex;gap:6px;align-items:center">
                <span class="hali-popup-badge" style="background:${colour}22;color:${colour}">
                  <span style="width:6px;height:6px;border-radius:50%;background:${colour};display:inline-block"></span>
                  ${sev.toUpperCase()}
                </span>
                <span style="font-size:11px;opacity:0.7">${(p.affected_countries ?? []).join(', ')}</span>
              </div>${population}`,
              { maxWidth: 260 },
            );
            // Alert polygons also swallow the map click, so trigger the
            // analysis explicitly — clicking a zone should both show its popup
            // and open the location report.
            layer.on('click', (e: L.LeafletMouseEvent) => {
              void runAnalysis(e.latlng.lat, e.latlng.lng);
            });
          },
        }).addTo(mapRef.current!);

        alertLayerRef.current = layer;
        setCount(geojson.features.length);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [lang, dayOffset, runAnalysis]);

  // ── Community report heatmap ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    fetchHeatmap(7)
      .then(async (heatData) => {
        if (heatLayerRef.current) mapRef.current?.removeLayer(heatLayerRef.current);
        const points = heatPoints(heatData);
        if (points.length > 0) {
          await import('leaflet.heat');
          const heat = (
            L as typeof L & {
              heatLayer: (p: [number, number, number][], o: Record<string, number>) => L.Layer;
            }
          ).heatLayer(points, { radius: 28, blur: 18, maxZoom: 10 });
          heat.addTo(mapRef.current!);
          heatLayerRef.current = heat;
        }
      })
      .catch(() => {});
  }, []);

  // ── Emerging hotspots (pulsing amber dots) ──────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    fetchEmergingHotspots()
      .then((data) => {
        if (hotspotLayerRef.current) mapRef.current?.removeLayer(hotspotLayerRef.current);
        if (data.features.length === 0) return;

        const group = L.layerGroup();
        for (const f of data.features) {
          const [lng, lat] = f.geometry.coordinates;
          const p = f.properties;
          L.marker([lat, lng], {
            icon: L.divIcon({
              className: 'hali-hotspot-icon',
              html: `<span class="hali-hotspot-dot" style="--hotspot-size:${Math.min(
                14 + p.report_count * 2,
                34,
              )}px"></span>`,
              iconSize: [0, 0],
            }),
          })
            .bindPopup(
              `<div class="hali-popup-title">${p.report_count} reports in this area</div>
               <div style="font-size:12px;margin-top:4px">No official alert issued.</div>
               <div style="font-size:12px">Dominant hazard: <strong>${p.dominant_hazard}</strong></div>
               <div style="font-size:11px;opacity:0.7;margin-top:4px">
                 First reported ${new Date(p.first_reported).toLocaleString()}
               </div>`,
              { maxWidth: 260 },
            )
            .addTo(group);
        }
        group.addTo(mapRef.current!);
        hotspotLayerRef.current = group;
      })
      .catch(() => {});
  }, []);

  // ── Compound risk choropleth ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    fetchCompoundRisk()
      .then((data) => {
        setRisk(data);
        if (riskLayerRef.current) mapRef.current?.removeLayer(riskLayerRef.current);
        if (data.features.length === 0) return;

        const max = Math.max(...data.features.map((f) => f.properties.compound_risk_score));
        const layer = L.geoJSON(data, {
          // Non-interactive on purpose. An interactive vector layer swallows the
          // click before it reaches the map, which would disable click-to-analyse
          // across every country the choropleth covers — i.e. most of the map.
          // The per-country numbers are already in the "Most at risk now" panel.
          interactive: false,
          style: (f) => ({
            color: '#64748b',
            weight: 1,
            fillColor: riskColour(f?.properties?.compound_risk_score ?? 0, max),
            fillOpacity: 0.35,
          }),
        });
        // Behind alert zones and hotspots, which are the primary signal.
        layer.addTo(mapRef.current!);
        layer.bringToBack();
        riskLayerRef.current = layer;
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
        {!loading && !error && (
          <div className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground shadow-sm">
            {count} alert{count !== 1 ? 's' : ''}
            {dayOffset != null ? ' in window' : ' active'}
          </div>
        )}
        {error && (
          <div className="flex items-center gap-1.5 rounded-full border border-destructive/20 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
            <AlertTriangle className="h-3 w-3" />
            Failed to load
          </div>
        )}
      </div>

      <div className="absolute bottom-6 left-3 z-[1000] flex flex-col gap-2">
        <TemporalSlider value={dayOffset} onChange={setDayOffset} />
        <RiskRanking data={risk} />
        <div className="rounded-lg border border-border bg-card/95 p-2.5 shadow-md backdrop-blur-sm">
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
          <div className="mt-1 flex items-center gap-2">
            <span className="hali-hotspot-legend" />
            <span className="text-[11px] text-muted-foreground">Emerging hotspot</span>
          </div>
        </div>
      </div>

      {panelOpen && (
        <AnalysisPanel
          analysis={analysis}
          loading={analysing}
          error={analysisError}
          onClose={() => setPanelOpen(false)}
        />
      )}

      <div
        ref={ref}
        className="h-full w-full"
        aria-label="HALI early warning map - East Africa"
        role="application"
      />
    </div>
  );
}
