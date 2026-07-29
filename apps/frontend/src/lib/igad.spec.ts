import { describe, it, expect } from 'vitest';
import {
  BOUNDARY_STYLE,
  IGAD_BOUNDS,
  IGAD_MIN_ZOOM,
  MASK_STYLE,
  igadMaskRings,
} from './igad';
import type { CountriesGeoJSON } from '@hali/types';

function collection(features: CountriesGeoJSON['features']): CountriesGeoJSON {
  return { type: 'FeatureCollection', features };
}

const square = (offset = 0): GeoJSON.Polygon => ({
  type: 'Polygon',
  coordinates: [
    [
      [35 + offset, 0],
      [36 + offset, 0],
      [36 + offset, 1],
      [35 + offset, 1],
      [35 + offset, 0],
    ],
  ],
});

const feature = (geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon, iso2 = 'KE') =>
  ({
    type: 'Feature' as const,
    geometry,
    properties: { iso2, name: 'Test' },
  }) as CountriesGeoJSON['features'][number];

describe('IGAD viewport', () => {
  it('covers every member state', () => {
    // Spot-check the extremes: Djibouti NE, southern Kenya, western Sudan.
    expect(IGAD_BOUNDS.contains([11.6, 43.1])).toBe(true); // Djibouti City
    expect(IGAD_BOUNDS.contains([-4.6, 39.7])).toBe(true); // Mombasa
    expect(IGAD_BOUNDS.contains([15.6, 32.5])).toBe(true); // Khartoum
    expect(IGAD_BOUNDS.contains([2.0, 45.3])).toBe(true); // Somalia
  });

  it('excludes places HALI does not cover', () => {
    expect(IGAD_BOUNDS.contains([6.5, 3.4])).toBe(false); // Lagos
    expect(IGAD_BOUNDS.contains([-26.2, 28.0])).toBe(false); // Johannesburg
  });

  it('keeps a minimum zoom that does not show the whole continent', () => {
    expect(IGAD_MIN_ZOOM).toBeGreaterThanOrEqual(4);
  });
});

describe('outside-IGAD mask', () => {
  it('starts with a world-covering ring', () => {
    const rings = igadMaskRings(collection([feature(square())]));
    const [world] = rings;
    const lats = world.map(([lat]) => lat);
    const lngs = world.map(([, lng]) => lng);

    expect(Math.min(...lats)).toBe(-90);
    expect(Math.max(...lats)).toBe(90);
    expect(Math.min(...lngs)).toBe(-180);
    expect(Math.max(...lngs)).toBe(180);
  });

  it('punches one hole per country polygon', () => {
    const rings = igadMaskRings(collection([feature(square(0)), feature(square(5), 'ET')]));
    expect(rings).toHaveLength(3); // world + 2 holes
  });

  it('punches one hole per part of a MultiPolygon', () => {
    const multi: GeoJSON.MultiPolygon = {
      type: 'MultiPolygon',
      coordinates: [square(0).coordinates, square(5).coordinates, square(10).coordinates],
    };
    const rings = igadMaskRings(collection([feature(multi)]));
    expect(rings).toHaveLength(4); // world + 3 islands
  });

  it('converts GeoJSON [lng, lat] to Leaflet [lat, lng]', () => {
    const rings = igadMaskRings(collection([feature(square())]));
    // GeoJSON gave [35, 0]; Leaflet must receive [0, 35].
    expect(rings[1][0]).toEqual([0, 35]);
  });

  it('ignores interior rings so lakes are not re-dimmed', () => {
    const withHole: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        square().coordinates[0],
        [
          [35.4, 0.4],
          [35.6, 0.4],
          [35.6, 0.6],
          [35.4, 0.6],
          [35.4, 0.4],
        ],
      ],
    };
    const rings = igadMaskRings(collection([feature(withHole)]));
    expect(rings).toHaveLength(2); // world + exterior only
  });

  it('skips degenerate rings rather than emitting broken geometry', () => {
    const degenerate = { type: 'Polygon', coordinates: [[[35, 0], [36, 0]]] } as GeoJSON.Polygon;
    expect(igadMaskRings(collection([feature(degenerate)]))).toHaveLength(1);
  });

  it('returns just the world ring when no countries load', () => {
    expect(igadMaskRings(collection([]))).toHaveLength(1);
  });
});

describe('layer styles', () => {
  it('draws boundaries hollow so overlays underneath stay visible', () => {
    // The original bbox boundaries were filled, which hid every ICPAC layer.
    expect(BOUNDARY_STYLE.fill).toBe(false);
  });

  it('makes both the mask and boundaries non-interactive', () => {
    // Either one intercepting clicks would disable click-to-analyse: the mask
    // covers the world, the boundaries cover all eight countries.
    expect(MASK_STYLE.interactive).toBe(false);
    expect(BOUNDARY_STYLE.interactive).toBe(false);
  });

  it('dims rather than hides what is outside the region', () => {
    expect(MASK_STYLE.fillOpacity).toBeGreaterThan(0);
    expect(MASK_STYLE.fillOpacity).toBeLessThan(1);
  });
});
