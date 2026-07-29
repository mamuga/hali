import { useCallback, useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { AlertTriangle, Loader2 } from 'lucide-react';
import {
  analyseLocation,
  fetchAlertsGeoJSON,
  fetchCompoundRisk,
  fetchCountriesGeoJSON,
  fetchEmergingHotspots,
  fetchHeatmap,
  queryPolygon,
} from '@/lib/api';
import { createBasemaps, DEFAULT_BASEMAP } from '@/lib/basemaps';
import {
  BOUNDARY_STYLE,
  IGAD_BOUNDS,
  IGAD_BOUNDS_PADDING,
  IGAD_MIN_ZOOM,
  MASK_STYLE,
  igadMaskRings,
} from '@/lib/igad';
import { createIcpacLayers } from '@/lib/icpacLayers';
import type {
  CommunityHeatmapFeatureCollection,
  CompoundRiskGeoJSON,
  Language,
  PolygonQueryResult,
  SpatialAnalysis,
} from '@hali/types';
import { AnalysisPanel } from './AnalysisPanel';
import { AoiPanel } from './AoiPanel';
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

/**
 * True while geoman has the map in draw, edit, drag, or removal mode.
 *
 * Read defensively off `map.pm`, which only exists once the lazily-imported
 * geoman chunk has loaded — before that, no mode can be active anyway.
 */
function isDrawing(map: L.Map): boolean {
  const pm = (map as L.Map & { pm?: Record<string, () => boolean> }).pm;
  if (!pm) return false;
  return Boolean(
    pm.globalDrawModeEnabled?.() ||
      pm.globalEditModeEnabled?.() ||
      pm.globalDragModeEnabled?.() ||
      pm.globalRemovalModeEnabled?.(),
  );
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
  const ipcLayerRef = useRef<L.GeoJSON | null>(null);
  const heatLayerRef = useRef<L.Layer | null>(null);
  const hotspotLayerRef = useRef<L.LayerGroup | null>(null);
  const riskLayerRef = useRef<L.GeoJSON | null>(null);
  const nationalLayerRef = useRef<L.GeoJSON | null>(null);
  const layerControlRef = useRef<L.Control.Layers | null>(null);
  // Overlays are created by independent effects that resolve in whatever order
  // the network returns, so each registers itself with the control as it lands
  // rather than the control waiting for all of them. Keyed by name so a layer
  // that gets rebuilt (alert zones, on language or playback change) replaces its
  // own entry instead of adding a duplicate row to the switcher.
  const registeredRef = useRef<Map<string, L.Layer>>(new Map());

  const [loading, setLoading] = useState(true);
  const [count, setCount] = useState(0);
  const [error, setError] = useState(false);
  const [dayOffset, setDayOffset] = useState<number | null>(null);
  const [risk, setRisk] = useState<CompoundRiskGeoJSON | null>(null);
  const [analysis, setAnalysis] = useState<SpatialAnalysis | null>(null);
  const [analysing, setAnalysing] = useState(false);
  const [analysisError, setAnalysisError] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [aoi, setAoi] = useState<PolygonQueryResult | null>(null);
  const [aoiLoading, setAoiLoading] = useState(false);
  const [aoiError, setAoiError] = useState<string | null>(null);
  const [aoiOpen, setAoiOpen] = useState(false);
  const aoiLayerRef = useRef<L.Layer | null>(null);

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

  const clearAoi = useCallback(() => {
    if (aoiLayerRef.current && mapRef.current) {
      mapRef.current.removeLayer(aoiLayerRef.current);
    }
    aoiLayerRef.current = null;
    setAoi(null);
    setAoiError(null);
    setAoiOpen(false);
  }, []);

  const runAoiQuery = useCallback(
    async (geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon) => {
      setAoiOpen(true);
      setAoiLoading(true);
      setAoiError(null);
      try {
        setAoi(await queryPolygon(geometry, langRef.current));
      } catch (err) {
        // The backend rejects oversized or malformed shapes with a 422 and a
        // human-readable reason — surface that rather than a generic failure.
        const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data
          ?.detail;
        const message =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail) && typeof detail[0]?.msg === 'string'
              ? String(detail[0].msg).replace(/^Value error,\s*/, '')
              : 'Could not analyse this area. Try drawing a smaller shape.';
        setAoiError(message);
        setAoi(null);
      } finally {
        setAoiLoading(false);
      }
    },
    [],
  );

  /** Add an overlay to the layer switcher, replacing any previous layer of that name. */
  const registerOverlay = useCallback((name: string, layer: L.Layer) => {
    const control = layerControlRef.current;
    if (!control) return;

    const previous = registeredRef.current.get(name);
    if (previous) control.removeLayer(previous);

    control.addOverlay(layer, name);
    registeredRef.current.set(name, layer);
  }, []);

  // ── Map bootstrap ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!ref.current || mapRef.current) return;

    const map = L.map(ref.current, {
      center: IGAD_BOUNDS.getCenter(),
      zoom: IGAD_MIN_ZOOM,
      minZoom: IGAD_MIN_ZOOM,
      maxBounds: IGAD_BOUNDS.pad(IGAD_BOUNDS_PADDING),
      maxBoundsViscosity: 0.75,
      // IGAD is ~30 deg tall and ~32 deg wide, so on most screens the latitude
      // binds and the ideal fit lands near zoom 4.7. With Leaflet's default
      // whole-number zoom that floors to 4, which overshoots the longitude by
      // more than double — the map opens showing Portugal and India. Quarter
      // steps let fitBounds actually land on the region.
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      // Canvas, not SVG. The feed is now 537 alerts — mostly FEWS NET district
      // polygons — and Leaflet's default SVG renderer creates one DOM path per
      // feature. Measured with SVG: a 2.9 s stall building the layer and 108 ms
      // p95 frames while panning. Canvas draws the same features into one
      // element, so cost scales with pixels rather than DOM nodes.
      preferCanvas: true,
    });

    // The zoom that just fits IGAD depends on the viewport's aspect ratio: the
    // region is 30 deg tall and 32 deg wide, so on a wide, short window Leaflet
    // fits the latitude and overflows the longitude badly — at a hardcoded
    // minZoom of 4 you could see India and Portugal either side of a region
    // that fits in neither. Deriving the floor from the actual fit keeps
    // "zoomed all the way out" meaning "IGAD fills the screen", at any size.
    const clampToRegion = () => {
      // On first run the container is often still 0x0 (the effect fires before
      // layout), which makes fitBounds pick the lowest possible zoom and then
      // setMinZoom locks that in — the map opens showing half the planet.
      // Measuring first, and running again on the next frame, corrects it.
      map.invalidateSize(false);
      map.setMinZoom(IGAD_MIN_ZOOM);
      map.fitBounds(IGAD_BOUNDS);
      map.setMinZoom(map.getZoom());
    };
    clampToRegion();
    const frame = requestAnimationFrame(clampToRegion);
    map.on('resize', clampToRegion);

    const basemaps = createBasemaps();
    basemaps[DEFAULT_BASEMAP].addTo(map);

    L.control.scale({ imperial: false }).addTo(map);

    // One control for everything: basemaps on top, then HALI's own overlays,
    // then ICPAC's authoritative layers. Expanded by default — a collapsed
    // control hides the fact that any of this exists.
    const control = L.control
      .layers(basemaps, createIcpacLayers(), { collapsed: false, position: 'topright' })
      .addTo(map);
    layerControlRef.current = control;

    map.on('click', (e: L.LeafletMouseEvent) => {
      // Every vertex placed while drawing is also a map click. Without this
      // guard, drawing a five-sided polygon fires five location analyses and
      // slides the wrong panel over the shape being drawn.
      if (isDrawing(map)) return;
      void runAnalysis(e.latlng.lat, e.latlng.lng);
    });

    mapRef.current = map;
    return () => {
      cancelAnimationFrame(frame);
      map.off('resize', clampToRegion);
      map.remove();
      mapRef.current = null;
      layerControlRef.current = null;
      registeredRef.current.clear();
    };
  }, [runAnalysis]);

  // ── Draw controls for area-of-interest analysis ─────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;

    // Lazy: geoman plus its CSS is ~140 KB, and the map is useful without it.
    void import('@/lib/aoi').then(({ enableDrawControls }) => {
      if (cancelled || !mapRef.current) return;

      enableDrawControls(map);

      map.on('pm:create', (e: { layer: L.Layer }) => {
        // One area at a time — a second shape would silently replace the
        // results panel while both outlines stayed on the map.
        if (aoiLayerRef.current) map.removeLayer(aoiLayerRef.current);
        aoiLayerRef.current = e.layer;

        const geojson = (e.layer as unknown as { toGeoJSON: () => GeoJSON.Feature }).toGeoJSON();
        const geometry = geojson.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon;
        void runAoiQuery(geometry);
      });

      // Re-run when the shape is dragged or reshaped, so the numbers always
      // describe the outline currently on screen.
      map.on('pm:edit', (e: { layer: L.Layer }) => {
        if (e.layer !== aoiLayerRef.current) return;
        const geojson = (e.layer as unknown as { toGeoJSON: () => GeoJSON.Feature }).toGeoJSON();
        void runAoiQuery(geojson.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon);
      });

      map.on('pm:remove', (e: { layer: L.Layer }) => {
        if (e.layer === aoiLayerRef.current) clearAoi();
      });
    });

    return () => {
      cancelled = true;
      map.off('pm:create');
      map.off('pm:edit');
      map.off('pm:remove');
    };
  }, [runAoiQuery, clearAoi]);

  // ── IGAD mask + hollow country outlines ─────────────────────────────────────
  useEffect(() => {
    if (!mapRef.current) return;
    let cancelled = false;

    fetchCountriesGeoJSON()
      .then((countries) => {
        const map = mapRef.current;
        if (cancelled || !map || countries.features.length === 0) return;

        // The mask paints only outside IGAD (the countries are holes), so it
        // never overlaps the choropleth, which paints only inside. Whichever
        // effect resolves last calls bringToBack() and the result looks the
        // same either way.
        const mask = L.polygon(igadMaskRings(countries), MASK_STYLE).addTo(map);
        mask.bringToBack();

        const boundaries = L.geoJSON(countries, { style: () => BOUNDARY_STYLE }).addTo(map);

        registerOverlay('Dim outside IGAD', mask);
        registerOverlay('IGAD boundaries', boundaries);
      })
      .catch(() => {
        // A missing mask is cosmetic; the alerts still render.
      });

    return () => {
      cancelled = true;
    };
  }, [registerOverlay]);

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

        // Split by scope. IFRC appeals and WHO outbreak notices carry a whole
        // national outline; drawn in the same layer as district footprints they
        // paint straight over them, which defeats the point of a subnational
        // map. They stay available, on their own toggle, drawn underneath and
        // outline-only.
        const isNational = (f: { properties?: { scope?: string } } | undefined) =>
          f?.properties?.scope === 'national';

        const ipcFeatures = {
          ...geojson,
          // FEWS NET publishes IPC food-security classifications as district
          // polygons. Keep them separate so a reviewer can inspect the
          // subnational food-insecurity layer without the other hazard feeds
          // obscuring it.
          features: geojson.features.filter((f) => f.properties?.source === 'fewsnet'),
        };
        const localFeatures = {
          ...geojson,
          features: geojson.features.filter(
            (f) => !isNational(f) && f.properties?.source !== 'fewsnet',
          ),
        };
        const nationalFeatures = {
          ...geojson,
          features: geojson.features.filter((f) => isNational(f)),
        };

        const bindAlert = (feature: GeoJSON.Feature, layer: L.Layer) => {
          const p = feature.properties;
          if (!p) return;
          const sev = p.severity ?? 'green';
          const colour = SEV_COLOUR[sev] ?? '#16a34a';
          const population =
            p.population_exposed != null
              ? `<div style="font-size:11px;opacity:0.75;margin-top:4px">~${Number(
                  p.population_exposed,
                ).toLocaleString()} people in zone</div>`
              : '';
          const scopeNote =
            p.scope === 'national'
              ? '<div style="font-size:11px;opacity:0.65;margin-top:4px">National advisory</div>'
              : '';
          layer.bindPopup(
            `<div class="hali-popup-title">${p.headline ?? `${p.hazard_type} alert`}</div>
            <div style="margin-top:6px;display:flex;gap:6px;align-items:center">
              <span class="hali-popup-badge" style="background:${colour}22;color:${colour}">
                <span style="width:6px;height:6px;border-radius:50%;background:${colour};display:inline-block"></span>
                ${sev.toUpperCase()}
              </span>
              <span style="font-size:11px;opacity:0.7">${(p.affected_countries ?? []).join(', ')}</span>
            </div>${population}${scopeNote}`,
            { maxWidth: 260 },
          );
          // Alert polygons also swallow the map click, so trigger the analysis
          // explicitly — clicking a zone should both show its popup and open
          // the location report.
          layer.on('click', (e: L.LeafletMouseEvent) => {
            void runAnalysis(e.latlng.lat, e.latlng.lng);
          });
        };

        const layer = L.geoJSON(localFeatures, {
          style: (f) => ({
            color: SEV_COLOUR[f?.properties?.severity ?? 'green'] ?? '#16a34a',
            fillColor: SEV_COLOUR[f?.properties?.severity ?? 'green'] ?? '#16a34a',
            fillOpacity: 0.35,
            weight: 1.5,
            opacity: 0.9,
          }),
          onEachFeature: bindAlert,
        }).addTo(mapRef.current!);

        if (nationalLayerRef.current) mapRef.current?.removeLayer(nationalLayerRef.current);
        const national = L.geoJSON(nationalFeatures, {
          style: (f) => ({
            color: SEV_COLOUR[f?.properties?.severity ?? 'green'] ?? '#16a34a',
            fill: false,
            weight: 2,
            opacity: 0.7,
            dashArray: '5 5',
          }),
          onEachFeature: bindAlert,
        });
        national.addTo(mapRef.current!);
        national.bringToBack();
        nationalLayerRef.current = national;
        registerOverlay('National advisories', national);

        alertLayerRef.current = layer;
        registerOverlay('Alert zones', layer);

        if (ipcLayerRef.current) mapRef.current?.removeLayer(ipcLayerRef.current);
        if (ipcFeatures.features.length > 0) {
          const ipcLayer = L.geoJSON(ipcFeatures, {
            style: (f) => {
              const severity = f?.properties?.severity ?? 'green';
              const colour = SEV_COLOUR[severity] ?? SEV_COLOUR.green;
              return {
                color: colour,
                fillColor: colour,
                fillOpacity: 0.55,
                weight: 1.2,
                opacity: 0.95,
              };
            },
            onEachFeature: bindAlert,
          });
          ipcLayer.addTo(mapRef.current!);
          ipcLayerRef.current = ipcLayer;
          registerOverlay('FEWS NET / IPC food insecurity', ipcLayer);
        }
        setCount(localFeatures.features.length);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [lang, dayOffset, runAnalysis, registerOverlay]);

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
          registerOverlay('Community heatmap', heat);
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
        registerOverlay('Emerging hotspots', group);
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
        registerOverlay('Compound risk', layer);
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
          <div className="mt-1 flex items-center gap-2">
            <span
              className="h-0 w-3 shrink-0 border-t-2"
              style={{ borderColor: BOUNDARY_STYLE.color }}
            />
            <span className="text-[11px] text-muted-foreground">IGAD boundary</span>
          </div>
        </div>
      </div>

      {/* The AOI panel wins when both are open: drawing a shape is a deliberate
          act, whereas a click-to-analyse can happen by accident while panning. */}
      {aoiOpen && (
        <AoiPanel
          result={aoi}
          loading={aoiLoading}
          error={aoiError}
          onClear={clearAoi}
          onClose={() => setAoiOpen(false)}
        />
      )}

      {panelOpen && !aoiOpen && (
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
