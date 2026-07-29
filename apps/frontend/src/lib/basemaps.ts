import L from 'leaflet';

/**
 * Basemaps offered in the layer switcher.
 *
 * GIS users expect to choose their own backdrop: imagery to verify what is
 * actually on the ground at a flood site, terrain to reason about where water
 * and landslides will go. All four are free and need no API key, which matters
 * because the app must keep working without a paid tile budget.
 *
 * `maxZoom` differs per provider and is not cosmetic — asking OpenTopoMap for
 * z18 returns 404s, which Leaflet renders as grey squares.
 */
export interface BasemapDef {
  label: string;
  url: string;
  attribution: string;
  maxZoom: number;
}

export const BASEMAPS: readonly BasemapDef[] = [
  {
    label: 'Streets (OSM)',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© <a href="https://openstreetmap.org">OpenStreetMap</a>',
    maxZoom: 18,
  },
  {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, Maxar, Earthstar Geographics',
    maxZoom: 18,
  },
  {
    label: 'Topographic',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '© <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
    maxZoom: 17,
  },
  {
    label: 'Terrain / Elevation',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri',
    maxZoom: 13,
  },
] as const;

/** The basemap shown on first load. */
export const DEFAULT_BASEMAP = BASEMAPS[0].label;

export function createBasemaps(): Record<string, L.TileLayer> {
  return Object.fromEntries(
    BASEMAPS.map((b) => [
      b.label,
      L.tileLayer(b.url, { attribution: b.attribution, maxZoom: b.maxZoom }),
    ]),
  );
}
