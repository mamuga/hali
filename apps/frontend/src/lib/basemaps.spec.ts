import { describe, it, expect } from 'vitest';
import { BASEMAPS, DEFAULT_BASEMAP, createBasemaps } from './basemaps';

describe('basemaps', () => {
  it('offers the four the GIS judges expect', () => {
    expect(BASEMAPS).toHaveLength(4);
    expect(BASEMAPS.map((b) => b.label)).toEqual([
      'Streets (OSM)',
      'Satellite',
      'Topographic',
      'Terrain / Elevation',
    ]);
  });

  it('defaults to a basemap that exists', () => {
    expect(BASEMAPS.some((b) => b.label === DEFAULT_BASEMAP)).toBe(true);
  });

  it('attributes every provider', () => {
    // Esri and OpenTopoMap both require attribution to be used for free.
    for (const b of BASEMAPS) {
      expect(b.attribution.length).toBeGreaterThan(0);
    }
  });

  it('sets a per-provider maxZoom', () => {
    // Requesting a zoom the provider does not serve returns 404s, which Leaflet
    // renders as grey squares rather than falling back.
    for (const b of BASEMAPS) {
      expect(b.maxZoom).toBeGreaterThanOrEqual(13);
      expect(b.maxZoom).toBeLessThanOrEqual(19);
    }
    expect(BASEMAPS.find((b) => b.label === 'Terrain / Elevation')?.maxZoom).toBe(13);
    expect(BASEMAPS.find((b) => b.label === 'Topographic')?.maxZoom).toBe(17);
  });

  it('uses https everywhere so the PWA is not blocked as mixed content', () => {
    for (const b of BASEMAPS) {
      expect(b.url.startsWith('https://')).toBe(true);
    }
  });

  it('requires no API key', () => {
    for (const b of BASEMAPS) {
      expect(b.url).not.toMatch(/(apikey|access_token|key=)/i);
    }
  });

  it('builds one Leaflet layer per definition', () => {
    const layers = createBasemaps();
    expect(Object.keys(layers)).toHaveLength(BASEMAPS.length);
    expect(layers[DEFAULT_BASEMAP]).toBeDefined();
  });
});
